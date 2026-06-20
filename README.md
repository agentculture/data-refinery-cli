# data-refinery-cli

Agent and CLI for **data quality in storage and retrieval** — validating,
deduplicating, and checking the integrity and freshness of data as it is stored
and fetched. Split out of [eidetic-cli](https://github.com/agentculture/eidetic-cli)
so eidetic keeps the agent-memory layer; sibling to
[daria](https://github.com/agentculture/daria), the Data Refinery Intelligent
Agent.

## What this owns

data-refinery-cli owns the **storage + data-quality infrastructure layer** for
the AgentCulture mesh (issue
[#1](https://github.com/agentculture/data-refinery-cli/issues/1)): the
mongo + neo4j substrate, the docker stack published to GHCR, and a
**consumer-agnostic** data-quality surface. It treats stored data as **opaque
documents** — it never interprets them as "memories." eidetic-cli is the first
consumer, over a subprocess-not-import boundary; the layer is reusable by any
agent that needs a dependency-light store plus quality checks.

The split ships in waves:

| Wave | Scope | Status |
|------|-------|--------|
| **1** | docker stack (mongo 27018 + neo4j 7687), GHCR publish, `stack` CLI verb, pinnable contract | **shipped** |
| **2** | generic storage envelope, files/cypher/mongo store adapters (optional `[store]` extra), data-quality verbs (validate, dedup, integrity, freshness) | planned |
| **3** | full pinnable verb contract + eidetic consumption over the process boundary | planned |

The runtime package has **no third-party dependencies** by default; the heavy
store drivers (`neo4j`, `pymongo`) arrive in Wave 2 behind an optional extra,
lazy-imported.

## Quickstart

```bash
uv sync
uv run pytest -n auto                  # run the test suite
uv run data-refinery stack up          # bring up mongo + neo4j (needs docker)
uv run data-refinery stack status --json
uv run data-refinery stack down
uv run data-refinery whoami            # identity from culture.yaml
uv run teken cli doctor . --strict     # the agent-first rubric gate CI runs
```

## CLI

| Verb | What it does |
|------|--------------|
| `stack up\|down\|status` | Manage the storage substrate (mongo + neo4j) via docker compose. |
| `whoami` | Report this agent's nick, version, backend, and model from `culture.yaml`. |
| `learn` | Print a structured self-teaching prompt. |
| `explain <path>` | Markdown docs for any noun/verb path. |
| `overview` | Read-only descriptive snapshot of the agent. |
| `doctor` | Check the agent-identity invariants (prompt-file-present, backend-consistency). |
| `cli overview` | Describe the CLI surface itself. |

Every command supports `--json`. Results go to stdout, errors/diagnostics to
stderr (never mixed). Exit codes: `0` success, `1` user error, `2` environment
error (e.g. docker absent — always with a `hint:`, never a traceback), `3+`
reserved.

## The storage stack

[`docker-compose.yml`](docker-compose.yml) brings up `mongo:8.0` on host port
**27018** (not 27017 — deliberate collision-avoidance) and `neo4j:5-community`
on **7687** (bolt) + **7474** (UI) with `apoc` and no auth. The ports and auth
match eidetic-cli's historical defaults exactly, so a consumer connects with
**zero config change**. It is published to GHCR as a versioned OCI artifact (and
attached to each release); see [`docs/stack-image.md`](docs/stack-image.md) for
the image name + tag scheme and [`docs/contract.md`](docs/contract.md) for the
contract a consumer pins.

## Names

Three names that differ on purpose:

- **CLI command** (the binary): `data-refinery`
- **PyPI dist + mesh nick**: `data-refinery-cli`
- **Python package / import**: `data_refinery`

`uv run data-refinery-cli …` fails — the binary is `data-refinery`. See
[`CLAUDE.md`](CLAUDE.md) for the full convention.

## Contributing

See [`CLAUDE.md`](CLAUDE.md) for the conventions that gate merges
(version-bump-every-PR, the `cicd` PR lane, `dependencies = []` invariant, the
agent-first rubric) and [`docs/skill-sources.md`](docs/skill-sources.md) for the
vendored skill provenance.

## License

Apache 2.0 — see [`LICENSE`](LICENSE).
