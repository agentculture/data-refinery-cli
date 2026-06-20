"""Consumer-agnostic data-quality checks over envelopes.

Pure functions (no I/O beyond an injected :class:`Backend`) so they are testable
as a library and shared by the CLI verbs. All return plain JSON-able dicts. None
of them rank or score — :func:`freshness` reports age/staleness **facts**, never
a ranking signal (the freshness *signal* stays in eidetic).
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from data_refinery.store.backend import Backend
from data_refinery.store.envelope import Envelope, content_hash

_VISIBILITIES = ("public", "private")


# -- validate (envelope shape) ------------------------------------------


def _scope_errors(scope: Any) -> list[str]:
    """Shape-check an optional ``scope`` sub-object; returns a list of errors.

    Split out of :func:`validate_payload` so the nested scope checks don't push
    that function's cognitive complexity over the limit.
    """
    if scope is None:
        return []
    if not isinstance(scope, dict):
        return ["scope: must be an object {name, visibility}"]
    errors: list[str] = []
    if not isinstance(scope.get("name", ""), str):
        errors.append("scope.name: must be a string")
    if scope.get("visibility", "public") not in _VISIBILITIES:
        errors.append(f"scope.visibility: must be one of {_VISIBILITIES}")
    return errors


def validate_payload(obj: Any) -> dict[str, Any]:
    """Validate a single raw envelope dict's shape. Returns ``{valid, errors}``."""
    if not isinstance(obj, dict):
        return {"valid": False, "errors": ["envelope must be a JSON object"]}
    errors: list[str] = []
    _id = obj.get("id")
    if not isinstance(_id, str) or not _id:
        errors.append("id: must be a non-empty string")
    if not isinstance(obj.get("content", ""), str):
        errors.append("content: must be a string")
    errors.extend(_scope_errors(obj.get("scope")))
    if obj.get("metadata") is not None and not isinstance(obj.get("metadata"), dict):
        errors.append("metadata: must be an object")
    if obj.get("hash") is not None and not isinstance(obj.get("hash"), str):
        errors.append("hash: must be a string")
    return {"valid": not errors, "errors": errors}


def validate_many(objs: list[Any]) -> dict[str, Any]:
    """Validate a list of raw envelope dicts. Returns ``{valid, count, results}``."""
    results: list[dict[str, Any]] = []
    for i, obj in enumerate(objs):
        r = validate_payload(obj)
        results.append(
            {
                "index": i,
                "id": obj.get("id") if isinstance(obj, dict) else None,
                "valid": r["valid"],
                "errors": r["errors"],
            }
        )
    return {
        "valid": all(r["valid"] for r in results) if results else True,
        "count": len(results),
        "results": results,
    }


# -- dedup (by id/hash, idempotent) -------------------------------------


def find_duplicate_groups(envelopes: list[Envelope]) -> list[dict[str, Any]]:
    """Group envelopes sharing a content hash **within the same scope**.

    Scope is part of the key so dedup never collapses a private document into a
    same-content public one (that would breach scope isolation). A group with
    more than one member is a genuine duplicate set: the first id is kept, the
    rest are redundant.
    """
    groups_map: dict[tuple[str, str, str], list[str]] = {}
    order: list[tuple[str, str, str]] = []
    for env in envelopes:
        key = (env.scope.name, env.scope.visibility, env.hash)
        if key not in groups_map:
            groups_map[key] = []
            order.append(key)
        groups_map[key].append(env.id)
    groups: list[dict[str, Any]] = []
    for key in order:
        ids = groups_map[key]
        if len(ids) > 1:
            name, vis, h = key
            groups.append(
                {
                    "scope": {"name": name, "visibility": vis},
                    "hash": h,
                    "ids": ids,
                    "kept": ids[0],
                    "removed": ids[1:],
                }
            )
    return groups


def dedup(backend: Backend) -> dict[str, Any]:
    """Collapse same-hash-same-scope envelopes to one survivor each.

    Idempotent: a second run over an already-deduped store finds no groups and
    removes nothing, leaving identical store state.
    """
    envelopes = backend.all()
    groups = find_duplicate_groups(envelopes)
    removed_ids: list[str] = []
    for group in groups:
        for rid in group["removed"]:
            if backend.delete(rid):
                removed_ids.append(rid)
    return {
        "duplicates_removed": len(removed_ids),
        "removed_ids": removed_ids,
        "kept": len(envelopes) - len(removed_ids),
        "groups": groups,
    }


# -- integrity (hash matches content) -----------------------------------


def integrity(envelopes: list[Envelope]) -> dict[str, Any]:
    """Check every stored hash against a fresh ``sha256(content)``."""
    mismatches: list[dict[str, str]] = []
    for env in envelopes:
        actual = content_hash(env.content)
        if actual != env.hash:
            mismatches.append({"id": env.id, "stored_hash": env.hash, "actual_hash": actual})
    return {"ok": not mismatches, "checked": len(envelopes), "mismatches": mismatches}


# -- freshness (age/staleness facts) ------------------------------------


def _parse_ts(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        dt = datetime.fromisoformat(value)
    except ValueError:
        return None
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=timezone.utc)


def freshness(
    envelopes: list[Envelope],
    *,
    field: str = "created",
    max_age: float | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Report the age (and optional staleness) of each envelope as *facts*.

    Reads an ISO-8601 timestamp from ``metadata[field]`` (data-refinery never
    owns temporal fields — the consumer names where its timestamp lives). Age is
    seconds relative to *now*; ``stale`` is ``age > max_age`` when ``max_age`` is
    given, else ``None``. This is a check, not a ranking signal.
    """
    if now is None:
        now = datetime.now(timezone.utc)
    elif now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    results: list[dict[str, Any]] = []
    stale_count = 0
    for env in envelopes:
        raw = env.metadata.get(field)
        ts = _parse_ts(raw)
        if ts is None:
            results.append(
                {
                    "id": env.id,
                    field: raw,
                    "age_seconds": None,
                    "stale": None,
                    "note": f"no parseable '{field}' timestamp in metadata",
                }
            )
            continue
        age = (now - ts).total_seconds()
        stale = bool(max_age is not None and age > max_age)
        if stale:
            stale_count += 1
        results.append({"id": env.id, field: raw, "age_seconds": age, "stale": stale})
    return {
        "checked": len(envelopes),
        "field": field,
        "max_age": max_age,
        "now": now.isoformat(),
        "stale": stale_count,
        "results": results,
    }
