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

The binary is `data-refinery` (the PyPI dist and mesh nick are
`data-refinery-cli`). The default runtime has no third-party dependencies; the
mongo/neo4j store backends live behind the optional `[store]` extra.

## Verbs

- `data-refinery whoami` — identity probe from `culture.yaml`.
- `data-refinery learn` — structured self-teaching prompt.
- `data-refinery explain <path>` — markdown docs for any noun/verb.
- `data-refinery overview` — descriptive snapshot of the agent.
- `data-refinery doctor` — check the agent-identity invariants.
- `data-refinery cli overview` — describe the CLI surface.
- `data-refinery stack up|down|status` — manage the storage substrate (mongo + neo4j).
- `data-refinery store put|get|list` — put/get/list opaque envelopes in the store.
- `data-refinery validate` — check envelope shape for JSON on stdin.
- `data-refinery dedup` — collapse same-hash-same-scope duplicates (idempotent).
- `data-refinery integrity` — check every stored hash matches sha256(content).
- `data-refinery freshness` — report age/staleness facts from a metadata timestamp.

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


_STORE = """\
# data-refinery store

Noun group that puts/gets/lists **storage-neutral envelopes** — the CLI mirror of
the importable `data_refinery.store` library (one shared implementation). An
envelope is `{id, hash, content, scope{name,visibility}, metadata}` with **no
memory semantics**: fields like `lifecycle`/`signal`/`created` ride inside
`metadata` and are never interpreted. The `hash` is `sha256(content)`, filled
automatically when omitted.

## Verbs

- `data-refinery store put` — upsert an envelope (JSON object on stdin, or
  `--id`/`--content`). Idempotent by id; dedups by hash on insert.
- `data-refinery store get <id>` — fetch an envelope visible to a scope. Returns
  `{...,"found":true}` or `{"id":…,"found":false}`.
- `data-refinery store list` — list envelopes visible to a scope.

## Backends & scope

- `--backend files` (default, dependency-free, `DR_DATA_DIR`) | `mongo` | `neo4j`
  (the last two need the optional `[store]` extra; an absent driver exits `2`
  with a `hint:`, never a traceback).
- `--scope`/`--visibility` select the scope. A **private**-scope document is
  never returned by a **public**-scope fetch (`can_serve`).

## Usage

    echo '{"id":"a","content":"hello"}' | data-refinery store put --json
    data-refinery store get a --json
    data-refinery store list --scope vault --visibility private --json
"""

_VALIDATE = """\
# data-refinery validate

Checks **envelope shape** for JSON piped on stdin (a single object or an array):
`id` is a non-empty string, `content` is a string, `scope.visibility` is
`public`/`private`, `metadata` is an object. A data-quality verb — it reports
facts and exits `0` when the check ran (findings ride in the payload).

## Usage

    echo '{"id":"a","content":"x"}' | data-refinery validate --json
    cat envelopes.json | data-refinery validate
"""

_DEDUP = """\
# data-refinery dedup

Collapses envelopes that share a content `hash` **within the same scope** to one
survivor (the first id is kept). **Idempotent**: running it twice over the same
store yields identical state and never a duplicate. Cross-scope same-content
documents are left alone (scope isolation).

## Usage

    data-refinery dedup --json
    data-refinery dedup --backend mongo --json
"""

_INTEGRITY = """\
# data-refinery integrity

Recomputes `sha256(content)` for every stored envelope and reports any mismatch
against the stored `hash`. Returns `{ok, checked, mismatches}`; exits `0` when
the check ran (`ok:false` signals tampered/corrupt content).

## Usage

    data-refinery integrity --json
    data-refinery integrity --backend neo4j --json
"""

_FRESHNESS = """\
# data-refinery freshness

Reports **age/staleness facts** — not a ranking signal. Reads an ISO-8601
timestamp from `metadata[--field]` (default `created`), computes age in seconds
vs now (`--now` overrides for determinism), and marks `stale` when older than
`--max-age` seconds. data-refinery never owns temporal fields; the consumer names
where its timestamp lives.

## Usage

    data-refinery freshness --field created --max-age 86400 --json
    data-refinery freshness --now 2026-06-20T00:00:00+00:00 --json
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
    ("store",): _STORE,
    ("store", "put"): _STORE,
    ("store", "get"): _STORE,
    ("store", "list"): _STORE,
    ("store", "overview"): _STORE,
    ("validate",): _VALIDATE,
    ("dedup",): _DEDUP,
    ("integrity",): _INTEGRITY,
    ("freshness",): _FRESHNESS,
}
