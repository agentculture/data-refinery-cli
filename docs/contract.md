# data-refinery-cli consumer contract

This is the surface a consumer (eidetic-cli first) may **pin against**. It is
versioned and governed by semver discipline: a change to any documented JSON
shape, exit-code meaning, or the image tag scheme requires a **version bump** in
[`pyproject.toml`](../pyproject.toml) (the `version-check` CI job enforces a bump
on every PR).

- **Contract version:** `1` (Wave 1 — infrastructure surface).
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

## Wave 2 — store + data-quality surface (NOT yet stable)

Added in Wave 2 (tracked as a follow-up issue). Reserved here so a consumer knows
what is coming and does not depend on a shape that does not exist yet:

- **Generic storage envelope** (opaque to data-refinery — no memory semantics):

  ```json
  {"id": "...", "hash": "...", "content": "...",
   "scope": {"name": "...", "visibility": "public|private"},
   "metadata": {}}
  ```

- **Store verbs:** `store put|get|list` (JSON in/out) and the matching importable
  library API `data_refinery.store.*`.
- **Data-quality verbs:** `validate`, `dedup` (idempotent by `id`/`hash`),
  `integrity`, `freshness` — JSON facts, consumer-agnostic.
- **Invariants the consumer can rely on:** idempotent dedup (never a duplicate by
  `id`/`hash`); the public/private scope **no-leak** (a private-scope document is
  never returned by a public-scope fetch).

> Wave 2 JSON shapes are **provisional** until that wave ships and this contract's
> version is incremented. Do not pin them yet.

## Versioning policy

| Change | Requires |
|--------|----------|
| New optional field in a JSON result | minor bump |
| Removed/renamed field, changed type, changed exit-code meaning | major bump |
| New verb | minor bump |
| Image tag-scheme change | major bump + doc update |

Consumers pin a package version (and an image tag) and re-validate this document
on upgrade.
