"""``data-refinery validate|dedup|integrity|freshness`` — data-quality verbs.

Consumer-agnostic checks over the store, mirroring :mod:`data_refinery.quality`.
All are global verbs (not a noun group) and all support ``--json``.

Exit policy (consistent with ``stack status``): the command exits ``0`` when the
check *ran* — findings ride in the payload (``valid: false`` / ``ok: false`` /
duplicate groups / stale counts). A non-zero exit means the command could not
run: ``1`` for unparseable input, ``2`` for a missing backend driver. No
traceback ever.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime

from data_refinery.cli._errors import EXIT_USER_ERROR, CliError
from data_refinery.cli._output import emit_result
from data_refinery.quality import checks
from data_refinery.store import get_backend

_BACKENDS = ("files", "mongo", "neo4j")


def _add_backend_flag(p: argparse.ArgumentParser) -> None:
    p.add_argument(
        "--backend",
        choices=_BACKENDS,
        default="files",
        help="Store backend (default: files; mongo/neo4j need the [store] extra).",
    )


def _add_json_flag(p: argparse.ArgumentParser) -> None:
    p.add_argument("--json", action="store_true", help="Emit structured JSON.")


def _read_stdin_json() -> object:
    if sys.stdin is None or sys.stdin.isatty():
        raise CliError(
            code=EXIT_USER_ERROR,
            message="validate expects a JSON envelope (or array) on stdin",
            remediation='pipe input, e.g. echo \'{"id":"a","content":"x"}\' | '
            "data-refinery validate",
        )
    raw = sys.stdin.read().strip()
    if not raw:
        raise CliError(
            code=EXIT_USER_ERROR,
            message="no input on stdin",
            remediation='pipe a JSON envelope or array, e.g. {"id":"a","content":"x"}',
        )
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise CliError(
            code=EXIT_USER_ERROR,
            message=f"invalid JSON on stdin: {exc}",
            remediation="pipe a single envelope object or a JSON array of them",
        ) from exc


def cmd_validate(args: argparse.Namespace) -> int:
    json_mode = bool(getattr(args, "json", False))
    payload = _read_stdin_json()
    objs = payload if isinstance(payload, list) else [payload]
    result = checks.validate_many(objs)
    if json_mode:
        emit_result(result, json_mode=True)
    else:
        valid_n = sum(1 for r in result["results"] if r["valid"])
        lines = [f"valid: {valid_n}/{result['count']}"]
        for r in result["results"]:
            if not r["valid"]:
                lines.append(f"- {r['id']}: {'; '.join(r['errors'])}")
        emit_result("\n".join(lines), json_mode=False)
    return 0


def cmd_dedup(args: argparse.Namespace) -> int:
    json_mode = bool(getattr(args, "json", False))
    result = checks.dedup(get_backend(args.backend))
    if json_mode:
        emit_result(result, json_mode=True)
    else:
        emit_result(
            f"dedup: removed {result['duplicates_removed']} duplicate(s), "
            f"{result['kept']} kept",
            json_mode=False,
        )
    return 0


def cmd_integrity(args: argparse.Namespace) -> int:
    json_mode = bool(getattr(args, "json", False))
    result = checks.integrity(get_backend(args.backend).all())
    if json_mode:
        emit_result(result, json_mode=True)
    else:
        lines = [f"ok: {result['ok']} ({result['checked']} checked)"]
        for m in result["mismatches"]:
            lines.append(f"- {m['id']}: stored {m['stored_hash'][:12]} != {m['actual_hash'][:12]}")
        emit_result("\n".join(lines), json_mode=False)
    return 0


def cmd_freshness(args: argparse.Namespace) -> int:
    json_mode = bool(getattr(args, "json", False))
    now = None
    if getattr(args, "now", None):
        try:
            now = datetime.fromisoformat(args.now)
        except ValueError as exc:
            raise CliError(
                code=EXIT_USER_ERROR,
                message=f"--now is not a valid ISO-8601 timestamp: {args.now}",
                remediation="pass e.g. --now 2026-06-20T00:00:00+00:00",
            ) from exc
    result = checks.freshness(
        get_backend(args.backend).all(),
        field=args.field,
        max_age=args.max_age,
        now=now,
    )
    if json_mode:
        emit_result(result, json_mode=True)
    else:
        emit_result(
            f"freshness: {result['checked']} checked, {result['stale']} stale "
            f"(field='{result['field']}', max_age={result['max_age']})",
            json_mode=False,
        )
    return 0


def register(sub: argparse._SubParsersAction) -> None:
    validate = sub.add_parser(
        "validate",
        help="Validate envelope shape for JSON piped on stdin (object or array).",
    )
    _add_json_flag(validate)
    validate.set_defaults(func=cmd_validate)

    dedup = sub.add_parser(
        "dedup",
        help="Collapse same-hash-same-scope duplicates in the store (idempotent).",
    )
    _add_backend_flag(dedup)
    _add_json_flag(dedup)
    dedup.set_defaults(func=cmd_dedup)

    integrity = sub.add_parser(
        "integrity",
        help="Check that every stored hash matches sha256(content).",
    )
    _add_backend_flag(integrity)
    _add_json_flag(integrity)
    integrity.set_defaults(func=cmd_integrity)

    freshness = sub.add_parser(
        "freshness",
        help="Report age/staleness facts from a metadata timestamp field.",
    )
    _add_backend_flag(freshness)
    freshness.add_argument(
        "--field",
        default="created",
        help="metadata key holding an ISO-8601 timestamp (default: created).",
    )
    freshness.add_argument(
        "--max-age",
        type=float,
        default=None,
        help="seconds; an envelope older than this is marked stale.",
    )
    freshness.add_argument(
        "--now",
        default=None,
        help="ISO-8601 'now' override (default: current UTC time). For determinism.",
    )
    _add_json_flag(freshness)
    freshness.set_defaults(func=cmd_freshness)
