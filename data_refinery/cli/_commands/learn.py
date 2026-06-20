"""``data-refinery learn`` — the learnability affordance.

Prints a structured self-teaching prompt. Must satisfy the agent-first rubric:
>=200 chars and mention purpose, command map, exit codes, --json, and explain.
"""

from __future__ import annotations

import argparse

from data_refinery import __version__
from data_refinery.cli._output import emit_result

_TEXT = """\
data-refinery — agent and CLI for data quality in storage and retrieval.

Purpose
-------
Validate, deduplicate, and check the integrity and freshness of data as it is
stored and fetched. Split out of eidetic-cli so eidetic keeps agent-memory;
sibling to daria. The store moves OPAQUE envelopes — no memory semantics. The
default runtime has no third-party dependencies; the mongo/neo4j store backends
live behind the optional [store] extra (lazy-imported).

Commands
--------
  data-refinery whoami             Identity from culture.yaml.
  data-refinery learn              This self-teaching prompt.
  data-refinery explain <path>...  Markdown docs for any noun/verb path.
  data-refinery overview           Descriptive snapshot of the agent.
  data-refinery doctor             Check the agent-identity invariants.
  data-refinery cli overview       Describe the CLI surface itself.
  data-refinery stack up|down|status   Manage the storage substrate.
  data-refinery store put|get|list     Put/get/list opaque envelopes.
  data-refinery validate           Check envelope shape (JSON on stdin).
  data-refinery dedup              Collapse same-hash duplicates (idempotent).
  data-refinery integrity          Check stored hash matches sha256(content).
  data-refinery freshness          Report age/staleness facts from metadata.

Machine-readable output
-----------------------
Every command supports --json. Errors in JSON mode emit
{"code", "message", "remediation"} to stderr. Stdout and stderr never mix.

Exit-code policy
----------------
  0 success
  1 user-input error (bad flag, bad path, missing arg)
  2 environment / setup error
  3+ reserved

More detail
-----------
  data-refinery explain data-refinery
"""


def _as_json_payload() -> dict[str, object]:
    return {
        "tool": "data-refinery",
        "version": __version__,
        "purpose": "Agent and CLI for data quality in storage and retrieval.",
        "commands": [
            {"path": ["whoami"], "summary": "Identity probe from culture.yaml."},
            {"path": ["learn"], "summary": "Self-teaching prompt."},
            {"path": ["explain"], "summary": "Markdown docs by path."},
            {"path": ["overview"], "summary": "Descriptive snapshot of the agent."},
            {"path": ["doctor"], "summary": "Check the agent-identity invariants."},
            {"path": ["cli", "overview"], "summary": "Describe the CLI surface."},
            {"path": ["stack"], "summary": "Manage the storage substrate (up/down/status)."},
            {"path": ["store"], "summary": "Put/get/list opaque envelopes in the store."},
            {"path": ["validate"], "summary": "Check envelope shape (JSON on stdin)."},
            {"path": ["dedup"], "summary": "Collapse same-hash duplicates (idempotent)."},
            {"path": ["integrity"], "summary": "Check stored hash matches sha256(content)."},
            {"path": ["freshness"], "summary": "Report age/staleness facts from metadata."},
        ],
        "exit_codes": {
            "0": "success",
            "1": "user-input error",
            "2": "environment/setup error",
        },
        "json_support": True,
        "explain_pointer": "data-refinery explain <path>",
    }


def cmd_learn(args: argparse.Namespace) -> int:
    if getattr(args, "json", False):
        emit_result(_as_json_payload(), json_mode=True)
    else:
        emit_result(_TEXT, json_mode=False)
    return 0


def register(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser(
        "learn",
        help="Print a structured self-teaching prompt for agent consumers.",
    )
    p.add_argument("--json", action="store_true", help="Emit structured JSON.")
    p.set_defaults(func=cmd_learn)
