"""Storage-neutral document envelope + scope policy for data-refinery's store.

The :class:`Envelope` is the generic, consumer-agnostic subset of what a stored
document carries: an ``id``, a ``content`` blob, a content ``hash``, a named
``scope`` with a visibility policy, and an opaque ``metadata`` bag. It
deliberately has **no memory semantics** — fields like ``lifecycle`` / ``signal``
/ ``recall_count`` / ``created`` are the *consumer's* concern and ride inside
``metadata``; data-refinery never interprets them.

:func:`can_serve` is the storage-neutral privacy invariant (the same scope
policy eidetic uses — itself originally cited *from* data-refinery): a private
document is served only to a query in the exact same scope; it never leaks to a
public scope or to any other scope.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Any, Literal, get_args

Visibility = Literal["public", "private"]
# Single source of truth for the allowed visibilities — derived from the type so
# the validation set can never drift from the `Visibility` literal.
_VISIBILITIES: tuple[str, ...] = get_args(Visibility)


@dataclass(frozen=True)
class Scope:
    """A named scope with a visibility policy."""

    name: str = "default"
    visibility: Visibility = "public"


DEFAULT_SCOPE: Scope = Scope()


def content_hash(content: str) -> str:
    """Deterministic SHA-256 hex digest of *content*."""
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


@dataclass
class Envelope:
    """A storage-neutral document: id + content + hash + scope + opaque metadata."""

    id: str
    content: str
    scope: Scope = DEFAULT_SCOPE
    metadata: dict[str, Any] = field(default_factory=dict)
    hash: str = ""

    def __post_init__(self) -> None:
        # Fill the content fingerprint when not supplied so `dedup`/`integrity`
        # always have a stable hash to reason about. Mirrors how eidetic's
        # Record fills its hash at construction.
        if not self.hash:
            object.__setattr__(self, "hash", content_hash(self.content))
        if not isinstance(self.metadata, dict):
            object.__setattr__(self, "metadata", {})

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "hash": self.hash,
            "content": self.content,
            "scope": {"name": self.scope.name, "visibility": self.scope.visibility},
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Envelope:
        scope_data = data.get("scope") or {}
        visibility = scope_data.get("visibility", DEFAULT_SCOPE.visibility)
        if visibility not in _VISIBILITIES:
            # Reject an unknown visibility at the ingestion boundary so a typo
            # ("privat", "secret", …) can never be silently coerced into a
            # servable record. `can_serve` also fails closed as a safety net,
            # but rejecting loudly here gives the operator a remediation. Lazy
            # import keeps envelope.py free of an import-time dep on the cli.
            from data_refinery.cli._errors import EXIT_USER_ERROR, CliError

            raise CliError(
                code=EXIT_USER_ERROR,
                message=f"scope.visibility must be one of {_VISIBILITIES}, got {visibility!r}",
                remediation='set scope.visibility to "public" or "private"',
            )
        scope = Scope(
            name=scope_data.get("name", DEFAULT_SCOPE.name),
            visibility=visibility,
        )
        return cls(
            id=data["id"],
            content=data.get("content", ""),
            scope=scope,
            metadata=data.get("metadata") or {},
            hash=data.get("hash", ""),
        )


def can_serve(query_scope: Scope, record_scope: Scope) -> bool:
    """Return True when *record_scope* may satisfy a query from *query_scope*.

    Only an explicitly **public** record is visible to any scope. A private
    record — *or* one whose visibility is unrecognised (the check **fails
    closed**) — is served only to a query in the *same* scope (matching name
    AND visibility); it never leaks to a public scope or to any other scope.
    This is the load-bearing no-leak invariant enforced identically by every
    backend's ``get``/``list``.
    """
    if record_scope.visibility == "public":
        return True
    return query_scope == record_scope
