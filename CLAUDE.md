# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

**data-refinery-cli** is an AgentCulture mesh agent: a CLI for **data quality in
storage and retrieval** — validating, deduplicating, and checking the integrity
and freshness of data as it is stored and fetched. It is being split out of
**eidetic-cli** so eidetic keeps the agent-memory layer; it is a sibling to
**daria** (the Data Refinery Intelligent Agent).

**Current state — read this first.** **Waves 1 and 2 of issue #1 are built.**
*Wave 1* (issue #1): the storage substrate (`docker-compose.yml` — mongo 27018 +
neo4j 7687/apoc) and the `data-refinery stack up/down/status` verb wrapping
`docker compose`, plus the GHCR publish workflow
(`.github/workflows/publish-stack.yml`) and the pinnable docs
(`docs/stack-image.md`, `docs/contract.md`). *Wave 2* (issue #3): the
storage-neutral **store** — the generic envelope (`data_refinery/store/`), the
importable `data_refinery.store.put/get/list` library mirrored by `data-refinery
store put/get/list`, and the files/mongo/neo4j adapters behind a `Backend`
Protocol; plus the **data-quality verbs** (`validate` / `dedup` / `integrity` /
`freshness` in `data_refinery/quality/`). Runtime `dependencies = []` still holds
— the `files` backend is stdlib-only (default) and `neo4j`/`pymongo` are
lazy-imported behind the optional `[store]` extra. The remaining code is the
inherited *agent-first introspection scaffold* (`whoami` / `learn` / `explain` /
`overview` / `doctor` + a `cli` noun), cited from
[teken](https://github.com/agentculture/teken)'s `python-cli` reference. **Wave
3** (the full pinnable verb-JSON contract + eidetic consuming the surface over
the subprocess boundary) is still open; the build order lives in **issue #1** /
**issue #3** (see "Domain roadmap").

## Names: there are three, and they differ on purpose

This trips up every change to the CLI surface. Keep them straight:

| Name | Value | Where it lives |
|------|-------|----------------|
| **CLI command** (the binary) | `data-refinery` | `[project.scripts]` in `pyproject.toml` — this is what you invoke: `uv run data-refinery whoami` |
| **PyPI dist + mesh nick** | `data-refinery-cli` | `pyproject.toml` `name`, `culture.yaml` `suffix`, the Sonar key `agentculture_data-refinery-cli`, `__version__` lookup, `_ISSUES_URL` |
| **Python package / import** | `data_refinery` | the `data_refinery/` dir, `import data_refinery`, `sonar.sources` |

`data-refinery-cli` is **not** an executable — `uv run data-refinery-cli …`
fails; the binary is `data-refinery`. The CLI's command-surface text (help,
`learn`, the `explain` catalog, `overview` subjects) and the README quickstart
all use `data-refinery`. The dist/nick name `data-refinery-cli` is kept as a
back-compat **alias** in the explain catalog (`explain data-refinery-cli` still
resolves) and as `whoami`'s nick. When you add a verb, keep this split: command
text → `data-refinery`, nick/dist/URL/`_pkg_version`/`_FALLBACK_NICK` →
`data-refinery-cli`.

## Common commands

```bash
uv sync                                   # create .venv, install runtime + dev deps
uv run pytest -n auto                      # full test suite (xdist parallel)
uv run pytest tests/test_cli.py::test_whoami_json   # a single test
uv run pytest -k explain                   # tests matching a name
uv run data-refinery whoami                # run the CLI (note: data-refinery, not -cli)
uv run data-refinery learn --json          # every verb supports --json
python -m data_refinery whoami             # equivalent module entry point
```

Lint / quality gates (each is its own CI job — run all before a PR):

```bash
uv run black --check data_refinery tests
uv run isort --check-only data_refinery tests
uv run flake8 data_refinery tests
uv run bandit -c pyproject.toml -r data_refinery
markdownlint-cli2 "**/*.md" "#node_modules" "#.local" "#.claude/skills" "#.teken"
uv run teken cli doctor . --strict         # the agent-first rubric gate (see below)
```

`black` / `isort` use line-length 100 (`pyproject.toml`); `flake8` matches it via
`.flake8`. Run `black`/`isort` without `--check` to auto-fix. For bulk markdown
fixes use the `lint-fix` agent.

## Architecture

The whole CLI is built around one contract: **an agent reading the output can
rely on it.** Structured errors, a strict stream split, `--json` everywhere, and
documented exit codes. The pieces that enforce this span several files:

- **`data_refinery/cli/__init__.py`** — `main(argv) -> int` is the entry point
  (`main(argv: list[str] | None = None)`, the contract teken checks). It builds an
  argparse tree, dispatches, and translates every failure to an exit code.
  - `_CliArgumentParser` overrides `.error()` so **argparse-level** failures
    (unknown verb, bad flag) route through the same `error:` / `hint:` structured
    format and exit 1 — not argparse's default `stderr` + exit 2. `parser_class`
    is propagated to every subparser so nested parse errors behave the same.
    Because parse errors happen *before* `args.json` exists, `main()` pre-scans
    raw argv for `--json` and sets the class-level `_json_hint`.
  - `_dispatch()` calls the handler; catches `CliError` → `emit_error`; wraps
    **any other exception** into a `CliError` so **no Python traceback ever
    leaks** to stderr (a hard rubric requirement).
- **`_errors.py`** — `CliError{code, message, remediation}` and the exit-code
  policy: `0` success, `1` user-input error, `2` environment/setup error, `3+`
  reserved. Every failure path raises `CliError`.
- **`_output.py`** — the strict stream split: `emit_result` → stdout,
  `emit_error` / `emit_diagnostic` → stderr, **never mixed**. In JSON mode each
  goes to its own stream as one JSON line. The `hint:` prefix on errors is
  load-bearing (agents and the rubric grep for it).
- **Command modules** in `cli/_commands/` each expose `register(sub)` and a
  handler returning `int | None`. To add a verb/noun: write the module, then call
  its `register()` in `_build_parser()`. Nouns with action-verbs must also expose
  an `overview` (rubric `overview_cli_noun_exists`) — the `cli` noun models that
  pattern with no action-verbs; **`stack`** (the Wave-1 noun) models a *real* one:
  `stack up/down/status` action-verbs plus `stack overview`.
- **`stack.py`** — manages the storage substrate by wrapping `docker compose`
  over the repo's `docker-compose.yml`. `find_compose()` walks up from `__file__`
  (mirroring `whoami.find_culture_yaml`) so it finds *this repo's* compose, not the
  caller's CWD; in a wheel install it returns `None` → `CliError(code=2)` pointing
  at the published OCI artifact. Docker absent / compose missing / compose failure
  all raise `CliError(code=2)` with a `hint:` — never a traceback. Uses only
  stdlib `subprocess`/`shutil`/`json` (no driver deps). The substrate ports/auth
  match eidetic's defaults exactly; the compose **project name is
  `data-refinery-stack`** (not `data-refinery`) to avoid colliding with the
  sibling `autonomous-intelligence/data-refinery` compose project.
- **`data_refinery/explain/`** — `catalog.py` holds verbatim markdown keyed by
  **command-path tuples** (`("whoami",)`, `("cli","overview")`); `resolve()`
  raises `CliError` on an unknown path. Every registered noun/verb needs an
  entry, and the root must be keyed under the **command name** `("data-refinery",)`
  (the rubric's `explain_self` runs `explain data-refinery`) — with
  `("data-refinery-cli",)` kept as a back-compat alias.
- **Identity without a YAML dependency.** `whoami.py` and `doctor.py` parse
  `culture.yaml` by hand (line-scanning, not PyYAML) to preserve the deps-empty
  invariant. `find_culture_yaml()` walks up from `__file__` to find *this agent's
  own* `culture.yaml` (not whatever is in the caller's CWD); in a wheel install
  none ships, so identity falls back to literal defaults.
- **`doctor`** mirrors the `steward doctor` invariants for a mesh agent:
  *prompt-file-present* + *backend-consistency* (`backend → prompt file`:
  `claude→CLAUDE.md`, `colleague→AGENTS.colleague.md`, `acp→AGENTS.md`,
  `gemini→GEMINI.md`) and a *skills-present* check. It returns the rubric-shaped
  `{healthy, checks:[{id,passed,severity,message,remediation}]}`.

### The agent-first rubric (`teken cli doctor . --strict`)

This is the **lint job's gate** and the design spec for the whole CLI. It checks
seven bundles — structure, learnability, json, errors, explain, overview, doctor
— against the *actual running CLI* (it invokes `data-refinery <verb>` and asserts
on output/exit codes). When you change the CLI surface, this is the fast check:
keep `learn` ≥200 chars with all markers, keep errors traceback-free with hints,
keep `explain <command-name>` resolving, keep every noun's `overview`.

## Identity & the two prompt files

`culture.yaml` declares the agent: `suffix: data-refinery-cli`,
**`backend: colleague`**, model `sakamakismile/Qwen3.6-27B-Text-NVFP4-MTP`. Two
prompt files coexist and serve different runtimes:

- **`CLAUDE.md`** (this file) — the prompt for **Claude Code** when a human (or
  you) operates in the repo interactively.
- **`AGENTS.colleague.md`** — the resident prompt for the **colleague backend**
  (the Qwen tool-loop peer that actually *runs* as this mesh agent). Because the
  declared backend is `colleague`, this is the file `doctor`/`steward` require,
  and it is currently a thin generic stub.

When you change durable agent behavior that should hold regardless of who runs
the agent, update **both** files (they target different runtimes but describe the
same agent). The seed version of this file claimed `backend: claude` — that was
stale; the live backend is `colleague`.

## Conventions that gate merges

- **Version-bump-every-PR.** Every PR — even docs/config/CI-only — must bump the
  `pyproject.toml` version, or the `version-check` CI job fails. Use the
  `version-bump` skill (updates `pyproject.toml` + prepends a Keep-a-Changelog
  entry to `CHANGELOG.md`). The check compares your version to `origin/main`.
- **Runtime deps stay empty.** `dependencies = []` is an invariant of the current
  scaffold; `teken` and the linters are **dev-only**. When the domain lands and
  needs `neo4j` / `pymongo` (issue #1), follow the sibling pattern proven across
  this org: put heavy deps behind an **optional extra**, **lazy-import** them
  inside function bodies, exit `CliError(code=2)` with an install `hint:` when
  absent, and add a static test asserting no top-level import of the optional dep.
- **No traceback, ever.** Failures raise `CliError`; the dispatcher wraps stray
  exceptions. Don't `print()` to stdout for errors or let exceptions escape.
- **`--json` on every command**, stdout/stderr never mixed.
- **SonarCloud coverage uses repo-relative paths.** `pyproject.toml`
  `[tool.coverage.run] relative_files = true, source = ["data_refinery"]` is what
  makes `coverage.xml` map onto `sonar.sources` — don't remove it. `omit` ≠ Sonar
  coverage exclusion; mirror any `omit` into `sonar.coverage.exclusions`.

### CI jobs (what must be green)

- `.github/workflows/tests.yml` → **test** (pytest + coverage, then SonarCloud
  scan gated on `SONAR_TOKEN`; `sonar.qualitygate.wait=true` fails the job on a
  red gate), **lint** (black, isort, flake8, bandit, markdownlint, **the teken
  rubric gate**), **version-check** (PR-only; enforces the bump).
- `.github/workflows/publish.yml` → TestPyPI on PRs, PyPI on push to `main`, via
  Trusted Publishing (OIDC, no tokens). Triggered by changes to `pyproject.toml`
  or `data_refinery/**`.

Use the **`cicd`** skill for the PR lifecycle (open / read / reply / status /
await SonarCloud); **`sonarclaude`** for quality-gate queries; **`run-tests`** to
run pytest. PR comments/issue posts auto-sign as `- data-refinery-cli (Claude)`.

## Skills (cite-don't-import)

`.claude/skills/` carries 12 skills vendored from **guildmaster** (the
AgentCulture skills supplier; `steward` keeps only the alignment role). They are
copied, not depended on — each consumer owns its copy. Provenance, per-skill
adaptation notes, and the re-sync procedure live in
[`docs/skill-sources.md`](docs/skill-sources.md). Two tracked divergences:
`agex→devex` and `outsource→ask-colleague` (vendored directly from `colleague`
until guildmaster re-broadcasts). Every `SKILL.md` must keep `type: command` in
frontmatter — `core.skill_loader` silently skips any that omit it.

Reach for **`ask-colleague`** reflexively: `review` for a diverse second opinion
on a committed diff before a PR, `explore` for a fresh read of an unfamiliar area
(both read-only, isolated in a throwaway worktree — always safe); `write --apply`
/ `--pr` mutates and needs the user's go-ahead. Optional `colleague` CLI on PATH.

## Domain roadmap (issue #1)

The agent's actual build order lives in
[issue #1](https://github.com/agentculture/data-refinery-cli/issues/1): take
ownership of the **storage + data-quality layer** split from eidetic-cli (this
returns the store substrate to its origin — eidetic's store/cypher/embedding
logic was *cited from* `data-refinery` in the first place). data-refinery-cli is
to own:

- a **`docker-compose.yml`** bringing up `mongo:8.0` on host port **27018** (not
  27017 — deliberate collision-avoidance, eidetic's defaults already point there)
  and `neo4j:5-community` (bolt 7687, apoc), and a **multi-arch GHCR image**
  bundling that stack;
- the **files backend** + **cypher/mongo store adapters**, and the
  **consumer-agnostic data-quality surface**: validate, dedup (by `id`/`hash`,
  idempotent upsert), integrity, freshness — with **no eidetic memory semantics
  leaking in**;
- the `neo4j` + `pymongo` runtime deps.

eidetic-cli keeps the record schema, the `remember`/`recall`/`sweep`/`migrate`
verbs, relevance scoring + the freshness *signal*, the no-hard-delete lifecycle,
and the per-scope public/private no-leak invariant — and becomes the **first
consumer** over a process (subprocess-not-import) boundary. Invariants your layer
must not break: idempotent dedup, and the public/private scope no-leak. The
proposed boundary is **phased**: ship the GHCR image first, move adapters + the
CLI surface second. Naming of the image and the store/quality verbs is this
repo's call (it owns the surface) but must be documented so eidetic can pin.

## Remaining gaps / next steps

Waves 1 and 2 of the split are built. *Wave 1* = the stack (compose + `stack`
verb + GHCR publish + contract docs). *Wave 2* (issue #3) = the store +
data-quality surface: the generic opaque envelope `{id,hash,content,scope,
metadata}` (`data_refinery/store/envelope.py`), the `Backend` Protocol +
files/mongo/neo4j adapters (`data_refinery/store/backends/`, the driver-backed
two behind the optional `[store]` extra, lazy-imported, `dependencies = []` stays
the default), the importable `data_refinery.store.put/get/list` mirrored by the
`store` CLI noun, and the `validate`/`dedup`/`integrity`/`freshness` verbs
(`data_refinery/quality/`). Idempotent dedup + the public/private scope no-leak
(`can_serve`, enforced by every backend's `get`/`list`) are the load-bearing
invariants. README, `AGENTS.colleague.md`, `learn`, `overview`, the explain
catalog, and `docs/contract.md` (now contract version 2) were updated for the
surface. What is still open:

1. **Wave 3 — the full pinnable verb contract + eidetic consumption** over the
   subprocess boundary (eidetic drops/thins `neo4j`+`pymongo`). The verb-JSON
   shapes are documented in `docs/contract.md`; Wave 3 freezes them as the pinned
   surface eidetic consumes process-to-process.

## Renaming / scaffold lineage

This repo descends from `culture-agent-template`; the template name is hard-coded
in ~100 places. To find every occurrence before a sweep:

```bash
git grep -nw data-refinery-cli        # dist/nick name
git grep -nw data_refinery            # python package
git grep -nw data-refinery            # CLI command
```
