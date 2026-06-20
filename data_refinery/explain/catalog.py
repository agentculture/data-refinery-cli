"""Markdown catalog for ``data-refinery explain <path>``.

Each entry is verbatim markdown. Keys are command-path tuples. The empty tuple
and ``("data-refinery",)`` both resolve to the root entry; ``("data-refinery-cli",)``
is kept as a back-compat alias for the dist/nick name.

Keep bodies self-contained: an agent reading one entry should get enough
context without chaining reads.
"""

from __future__ import annotations

_ROOT = """\
# data-refinery

Agent and CLI for **data quality in storage and retrieval** — validating,
deduplicating, and checking the integrity and freshness of data as it is stored
and fetched. Split out of eidetic-cli so eidetic keeps agent-memory; sibling to
daria, the Data Refinery Intelligent Agent.

The data-quality verbs are not built yet (see issue #1). Today this exposes the
agent-first introspection surface below on a self-contained runtime (no
third-party dependencies). The binary is `data-refinery` (the PyPI dist and mesh
nick are `data-refinery-cli`).

## Verbs

- `data-refinery whoami` — identity probe from `culture.yaml`.
- `data-refinery learn` — structured self-teaching prompt.
- `data-refinery explain <path>` — markdown docs for any noun/verb.
- `data-refinery overview` — descriptive snapshot of the agent.
- `data-refinery doctor` — check the agent-identity invariants.
- `data-refinery cli overview` — describe the CLI surface.
- `data-refinery stack up|down|status` — manage the storage substrate (mongo + neo4j).

## Exit-code policy

- `0` success
- `1` user-input error
- `2` environment / setup error
- `3+` reserved

## See also

- `data-refinery explain whoami`
- `data-refinery explain doctor`
"""

_WHOAMI = """\
# data-refinery whoami

Reports the agent's identity from `culture.yaml`: nick (`suffix`), backend,
served model, and the package version. Read-only.

## Usage

    data-refinery whoami
    data-refinery whoami --json
"""

_LEARN = """\
# data-refinery learn

Prints a structured self-teaching prompt covering purpose, command map,
exit-code policy, `--json` support, and the `explain` pointer.

## Usage

    data-refinery learn
    data-refinery learn --json
"""

_EXPLAIN = """\
# data-refinery explain <path>

Prints markdown documentation for any noun/verb path. Unlike `--help` (terse,
positional), `explain` is global and addressable by path.

## Usage

    data-refinery explain data-refinery
    data-refinery explain whoami
    data-refinery explain --json <path>
"""

_OVERVIEW = """\
# data-refinery overview

Read-only descriptive snapshot of the agent: identity (from `culture.yaml`), the
verb surface, and the sibling-pattern artifacts the agent carries. Accepts an
ignored `target` so a stray path never hard-fails.

## Usage

    data-refinery overview
    data-refinery overview --json
"""

_DOCTOR = """\
# data-refinery doctor

Checks the agent-identity invariants `steward doctor` verifies:
prompt-file-present and backend-consistency (`colleague` → `AGENTS.colleague.md`),
plus a skills-present check. Exits 1 when unhealthy.

## Usage

    data-refinery doctor
    data-refinery doctor --json
"""

_CLI = """\
# data-refinery cli

Noun group for CLI-surface introspection. `cli overview` describes the CLI
itself (distinct from the global `overview`, which describes the agent).

## Usage

    data-refinery cli overview
    data-refinery cli overview --json
"""


_STACK = """\
# data-refinery stack

Noun group that manages the **storage substrate** data-refinery owns (issue #1):
`mongo:8.0` on host port **27018** and `neo4j:5-community` on **7687** (bolt) +
**7474** (browser UI), apoc, no auth. Wraps `docker compose` over this repo's
`docker-compose.yml` so the agent manages the infra without hand-rolling compose.

The ports/auth match eidetic-cli's historical defaults exactly, so a consumer
connects with zero config change.

## Verbs

- `data-refinery stack up` — `docker compose up -d` (bring the stack up).
- `data-refinery stack down` — `docker compose down` (stop the stack).
- `data-refinery stack status` — per-service state + health (`--json` for structured).

## Behaviour

- `--json` on every verb; results to stdout, diagnostics to stderr.
- Docker absent, compose file missing, or a compose failure → exit `2`
  (environment error) with a `hint:` — never a Python traceback.

## Usage

    data-refinery stack up
    data-refinery stack status --json
    data-refinery stack down
"""


ENTRIES: dict[tuple[str, ...], str] = {
    (): _ROOT,
    ("data-refinery",): _ROOT,
    # Back-compat alias for the dist/nick name (the binary is `data-refinery`).
    ("data-refinery-cli",): _ROOT,
    ("whoami",): _WHOAMI,
    ("learn",): _LEARN,
    ("explain",): _EXPLAIN,
    ("overview",): _OVERVIEW,
    ("doctor",): _DOCTOR,
    ("cli",): _CLI,
    ("cli", "overview"): _CLI,
    ("stack",): _STACK,
    ("stack", "up"): _STACK,
    ("stack", "down"): _STACK,
    ("stack", "status"): _STACK,
    ("stack", "overview"): _STACK,
}
