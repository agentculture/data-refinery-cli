"""``data-refinery store`` — put/get/list opaque envelopes in the store.

The ``store`` noun is the CLI mirror of the importable :mod:`data_refinery.store`
library — both share one implementation. It moves storage-neutral
:class:`~data_refinery.store.envelope.Envelope` documents (id + content + hash +
scope + opaque metadata); it never interprets them as memories.

Contract (agent-first): ``--json`` on every verb; results to stdout,
diagnostics to stderr; an absent optional driver (``mongo`` / ``neo4j`` without
the ``[store]`` extra) exits code ``2`` with a ``hint:`` and never a traceback.
"""

from __future__ import annotations

import argparse
import json
import sys

from data_refinery.cli._errors import EXIT_USER_ERROR, CliError
from data_refinery.cli._output import emit_result
from data_refinery.store import get_backend
from data_refinery.store.envelope import DEFAULT_SCOPE, Envelope, Scope

_BACKENDS = ("files", "mongo", "neo4j")


def _scope_from_args(args: argparse.Namespace) -> Scope:
    return Scope(
        name=getattr(args, "scope", None) or DEFAULT_SCOPE.name,
        visibility=getattr(args, "visibility", None) or DEFAULT_SCOPE.visibility,
    )


def _read_stdin_json() -> dict | None:
    """Parse a single JSON envelope object piped on stdin, or None if no input."""
    if sys.stdin is None or sys.stdin.isatty():
        return None
    raw = sys.stdin.read().strip()
    if not raw:
        return None
    try:
        obj = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise CliError(
            code=EXIT_USER_ERROR,
            message=f"invalid JSON on stdin: {exc}",
            remediation='pipe an envelope object like {"id":"a","content":"hello"}',
        ) from exc
    if not isinstance(obj, dict):
        raise CliError(
            code=EXIT_USER_ERROR,
            message="stdin JSON must be a single envelope object",
            remediation='pipe an object like {"id":"a","content":"hello"}',
        )
    return obj


def _envelope_from_args(args: argparse.Namespace) -> Envelope:
    """Build an Envelope from a piped JSON object, else from --id/--content flags."""
    payload = _read_stdin_json()
    if payload is not None:
        if not payload.get("id"):
            raise CliError(
                code=EXIT_USER_ERROR,
                message="envelope on stdin is missing 'id'",
                remediation='include "id" in the JSON, e.g. {"id":"a","content":"hello"}',
            )
        return Envelope.from_dict(payload)
    if not getattr(args, "id", None):
        raise CliError(
            code=EXIT_USER_ERROR,
            message="no envelope provided",
            remediation="pipe a JSON envelope on stdin, or pass --id (and --content)",
        )
    return Envelope(id=args.id, content=args.content or "", scope=_scope_from_args(args))


def cmd_store_put(args: argparse.Namespace) -> int:
    json_mode = bool(getattr(args, "json", False))
    backend = get_backend(args.backend)
    envelope = _envelope_from_args(args)
    backend.upsert(envelope)
    if json_mode:
        emit_result(envelope.to_dict(), json_mode=True)
    else:
        scope = envelope.scope
        emit_result(
            f"stored {envelope.id} ({scope.name}/{scope.visibility}) hash={envelope.hash[:12]}",
            json_mode=False,
        )
    return 0


def cmd_store_get(args: argparse.Namespace) -> int:
    json_mode = bool(getattr(args, "json", False))
    backend = get_backend(args.backend)
    envelope = backend.get(args.id, _scope_from_args(args))
    if json_mode:
        if envelope is None:
            emit_result({"id": args.id, "found": False}, json_mode=True)
        else:
            payload = envelope.to_dict()
            payload["found"] = True
            emit_result(payload, json_mode=True)
    else:
        emit_result(
            f"not found: {args.id}" if envelope is None else envelope.content, json_mode=False
        )
    return 0


def cmd_store_list(args: argparse.Namespace) -> int:
    json_mode = bool(getattr(args, "json", False))
    backend = get_backend(args.backend)
    envelopes = backend.list(_scope_from_args(args))
    if json_mode:
        emit_result([e.to_dict() for e in envelopes], json_mode=True)
    elif not envelopes:
        emit_result("(empty)", json_mode=False)
    else:
        lines = [
            f"- {e.id} ({e.scope.name}/{e.scope.visibility}) hash={e.hash[:12]}" for e in envelopes
        ]
        emit_result("\n".join(lines), json_mode=False)
    return 0


def _store_overview(args: argparse.Namespace) -> int:
    """`data-refinery store` with no sub-verb prints the noun's overview."""
    from data_refinery.cli._commands.overview import emit_overview

    sections = [
        {
            "title": "Verbs",
            "items": [
                "store put — upsert an envelope (JSON on stdin, or --id/--content)",
                "store get <id> — fetch an envelope visible to a scope",
                "store list — list envelopes visible to a scope",
            ],
        },
        {
            "title": "Envelope",
            "items": [
                "storage-neutral: {id, hash, content, scope{name,visibility}, metadata}",
                "no memory semantics — lifecycle/signal/etc. ride inside metadata",
                "hash is sha256(content), filled automatically when absent",
            ],
        },
        {
            "title": "Backends",
            "items": [
                "files — dependency-free JSONL (default; DR_DATA_DIR)",
                "mongo / neo4j — behind the optional [store] extra (lazy-imported)",
            ],
        },
        {
            "title": "Conventions",
            "items": [
                "every verb supports --json",
                "private-scope docs never leak to a public-scope fetch (can_serve)",
                "missing [store] driver → exit 2 with a hint:, never a traceback",
            ],
        },
    ]
    emit_overview("data-refinery store", sections, json_mode=bool(getattr(args, "json", False)))
    return 0


def _add_scope_flags(p: argparse.ArgumentParser) -> None:
    p.add_argument("--scope", help="Scope name (default: 'default').")
    p.add_argument(
        "--visibility",
        choices=("public", "private"),
        help="Scope visibility (default: public).",
    )


def _add_backend_flag(p: argparse.ArgumentParser) -> None:
    p.add_argument(
        "--backend",
        choices=_BACKENDS,
        default="files",
        help="Store backend (default: files; mongo/neo4j need the [store] extra).",
    )


def _add_json_flag(p: argparse.ArgumentParser) -> None:
    p.add_argument("--json", action="store_true", help="Emit structured JSON.")


def register(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser("store", help="Put/get/list opaque envelopes in the store.")
    _add_json_flag(p)
    p.set_defaults(func=_store_overview, json=False)
    # Propagate the structured-error parser_class to nested verbs.
    verb = p.add_subparsers(dest="store_command", parser_class=type(p))

    put = verb.add_parser("put", help="Upsert an envelope (JSON on stdin or --id/--content).")
    put.add_argument("--id", help="Envelope id (when not piping JSON).")
    put.add_argument("--content", help="Envelope content (when not piping JSON).")
    _add_scope_flags(put)
    _add_backend_flag(put)
    _add_json_flag(put)
    put.set_defaults(func=cmd_store_put)

    get_p = verb.add_parser("get", help="Fetch an envelope by id (scope-filtered).")
    get_p.add_argument("id", help="Envelope id to fetch.")
    _add_scope_flags(get_p)
    _add_backend_flag(get_p)
    _add_json_flag(get_p)
    get_p.set_defaults(func=cmd_store_get)

    list_p = verb.add_parser("list", help="List envelopes visible to a scope.")
    _add_scope_flags(list_p)
    _add_backend_flag(list_p)
    _add_json_flag(list_p)
    list_p.set_defaults(func=cmd_store_list)

    ov = verb.add_parser("overview", help="Describe the store noun.")
    _add_json_flag(ov)
    ov.set_defaults(func=_store_overview)
