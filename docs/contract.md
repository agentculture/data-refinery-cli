# data-refinery-cli consumer contract

This is the surface a consumer (eidetic-cli first) may **pin against**. It is
versioned and governed by semver discipline: a change to any documented JSON
shape, exit-code meaning, or the image tag scheme requires a **version bump** in
[`pyproject.toml`](../pyproject.toml) (the `version-check` CI job enforces a bump
on every PR).

- **Contract version:** `2` (Wave 2 — adds the store + data-quality surface to
  the Wave 1 infrastructure surface).
- **Package version pinned by a consumer:** see `pyproject.toml` `version`.

## Wave 1 — the storage stack (stable)

### Image / OCI artifact

Documented in full in [`docs/stack-image.md`](stack-image.md). Summary a consumer
can pin:

- **Name:** `ghcr.io/agentculture/data-refinery-stack`
- **Tag scheme:** release version without leading `v` (e.g. `0.4.0`); `latest`
  floats. A version tag is immutable.
- **Ports/auth (pinnable):** mongo `27018`, neo4j `7687` (bolt) + `7474` (UI),
  `apoc`, no auth — matching eidetic's defaults so its env connects unchanged.
  Ports bind to **`127.0.0.1` only** by default (the DBs are unauthenticated);
  set `DR_BIND=0.0.0.0` to expose on all interfaces on a trusted network.

### `data-refinery stack` verbs (stable)

All verbs accept `--json`. Results → stdout, diagnostics → stderr, never mixed.

`data-refinery stack status --json`:

```json
{
  "compose_file": "/abs/path/docker-compose.yml",
  "running": false,
  "healthy": false,
  "services": [
    {"name": "data-refinery-mongo", "service": "mongo",
     "state": "running", "health": "healthy", "status": "Up 3 minutes"}
  ],
  "command": "status"
}
```

`data-refinery stack up --json` → the `status` payload with `"command": "up"`.
`data-refinery stack down --json` → `{"command": "down", "compose_file": "...", "running": false}`.

### Exit codes (stable)

- `0` success
- `1` user-input error (bad flag, unknown verb/path)
- `2` environment/setup error (docker absent, compose missing, compose failed) —
  always accompanied by a `hint:` on stderr; **never a Python traceback**.
- `3+` reserved

## Wave 2 — store + data-quality surface (stable)

The store moves **opaque** documents — data-refinery never interprets them as
memories. All verbs accept `--json`; results → stdout, diagnostics/errors →
stderr, never mixed. The same implementation is importable as
`data_refinery.store.*` / `data_refinery.quality.*` (a consumer may shell out OR
import).

### Generic storage envelope

```json
{"id": "...", "hash": "...", "content": "...",
 "scope": {"name": "...", "visibility": "public|private"},
 "metadata": {}}
```

`hash` is `sha256(content)`, filled when omitted. `scope.visibility` is
constrained to exactly `public` or `private`: an envelope carrying any other
value is **rejected at ingestion** (`store put` / the importable API exit code
`1` with a `hint:`). The privacy check itself **fails closed** — only an
explicitly `public` record is served across scopes; a `private` record (or any
unrecognised visibility) is served only to a query in the *same* scope. There
are **no** memory fields: a consumer's `lifecycle` / `signal` / `recall_count` /
`created` ride inside `metadata` and are never read by data-refinery.

### `data-refinery store` verbs

- `store put` — reads a JSON envelope on stdin (or `--id`/`--content` flags),
  upserts (idempotent by `id`; on insert, dedups by `hash` **within the same
  scope** — identical content under a new id collapses to one survivor;
  identical across backends), echoes the stored envelope. `--backend
  files|mongo|neo4j` (default `files`).
- `store get <id> --json` → the envelope plus `"found": true`, or
  `{"id": "...", "found": false}`. Scope-filtered (`--scope`/`--visibility`).
- `store list --json` → a JSON array of envelopes visible to the scope.

### `data-refinery` data-quality verbs

- `validate` (stdin: object or array) → `{"valid", "count", "results":[{index,id,valid,errors}]}`.
- `dedup --backend … --json` → `{"duplicates_removed", "removed_ids", "kept", "groups"}`.
  Idempotent: a second run removes 0.
- `integrity --backend … --json` → `{"ok", "checked", "mismatches":[{id,stored_hash,actual_hash}]}`.
- `freshness --field <k> --max-age <s> [--now <iso>] --json` →
  `{"checked", "field", "max_age", "now", "stale", "results":[{id, <k>, age_seconds, stale}]}`.
  Age/staleness **facts**, not a ranking signal.

Each data-quality verb exits `0` when the check *ran* (findings ride in the
payload, e.g. `valid:false` / `ok:false`); `1` for unparseable input; `2` for a
missing backend driver.

### Backends + the optional `[store]` extra

`files` is dependency-free (default; data dir via `DR_DATA_DIR`). `mongo`
(`DR_MONGO_URI`, default `mongodb://localhost:27018`) and `neo4j` (`DR_NEO4J_URI`,
default `bolt://localhost:7687`) need the optional extra:

```bash
pip install 'data-refinery-cli[store]'
```

A store/quality verb selecting `--backend mongo|neo4j` without the extra exits
`2` with an install `hint:` — never a traceback.

### Invariants the consumer can rely on

- **Idempotent dedup** — running it twice over the same store yields identical
  state and never a duplicate by `id` or `hash` (within a scope).
- **Public/private scope no-leak** — a private-scope document is **never**
  returned by a public-scope `get`/`list` (`can_serve` is enforced by every
  backend, not just the consumer).

## Versioning policy

| Change | Requires |
|--------|----------|
| New optional field in a JSON result | minor bump |
| Removed/renamed field, changed type, changed exit-code meaning | major bump |
| New verb | minor bump |
| Image tag-scheme change | major bump + doc update |

Consumers pin a package version (and an image tag) and re-validate this document
on upgrade.
