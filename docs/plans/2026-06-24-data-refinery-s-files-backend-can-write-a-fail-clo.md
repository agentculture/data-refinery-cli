# Build Plan — data-refinery's files backend can write a fail-closed .gitignore on store-dir materialization, so a consumer keeps private shards out of git without ever constructing a write path itself

slug: `data-refinery-s-files-backend-can-write-a-fail-clo` · status: `exported` · from frame: `data-refinery-s-files-backend-can-write-a-fail-clo`

> data-refinery's files backend can write a fail-closed .gitignore on store-dir materialization, so a consumer keeps private shards out of git without ever constructing a write path itself

## Tasks

### t1 — Core files-backend .gitignore support + unit/integration tests

- covers: c1, c5, c6, c8, c9, h1, h2, h3, h6, h8, h10, h11, h12
- acceptance:
  - FilesBackend(base_dir, write_gitignore=True) creates base_dir/.gitignore on the first upsert with exactly the bytes '*\n!.gitignore\n!*__public.jsonl\n'
  - default write_gitignore=False writes no .gitignore; the materialized dir is byte-identical to current behavior (regression test)
  - get()/list() never create .gitignore even when write_gitignore=True (gitignore lives on write paths only, never in __init__)
  - an existing .gitignore is never overwritten even when its content differs from the whitelist (create-when-absent)
  - in a temp git repo: git check-ignore reports <scope>__private.jsonl and an arbitrary non-public sidecar name ignored, and <scope>__public.jsonl tracked
  - files.build(base_dir=..., write_gitignore=...) honors both kwargs (no longer dropped); store.put/get/list forward them through get_backend
  - mongo/neo4j backends remain unaffected (no .gitignore behavior); a re-run after the file exists writes nothing

### t2 — Plumb write_gitignore + base_dir through store.migrate

- depends on: t1
- covers: c3
- acceptance:
  - store.migrate(transform, backend='files', base_dir=..., write_gitignore=True) materializes base_dir/.gitignore during the apply pass
  - dry_run=True writes nothing, including no .gitignore
  - migrate() signature gains write_gitignore: bool = False; with it off, migrate is byte-identical to today

### t3 — Docs + version bump + CHANGELOG for the opt-in surface

- depends on: t1, t2
- covers: c4, c7, h9, h12
- acceptance:
  - docs/contract.md documents write_gitignore on the files put/migrate surface: the fail-closed whitelist, create-when-absent, and the mongo/neo4j no-op
  - README.md + AGENTS.colleague.md note the opt-in; CHANGELOG.md gains an Added entry; pyproject.toml version is bumped so version-check passes
  - the rationale (DR owns the layout so DR owns the ignore pattern; moves eidetic's S2083 sink) is captured in the contract doc

### t4 — Cross-check eidetic-cli can reach write_gitignore via the importable surface

- covers: c2, h7
- acceptance:
  - eidetic-cli's store consumption call sites are inspected and confirmed able to pass write_gitignore via store.migrate/store.put with a base_dir it owns (Option B); if not, a follow-up issue is filed naming the surface eidetic needs
  - the tagged-release floor eidetic will pin is identified (the version this ships in)

## Risks

- [unknown_nonblocking] git check-ignore acceptance tests require a git binary; the test must skip gracefully when git is absent rather than fail (task t1)
- [unknown_nonblocking] t4 inspects sibling repo eidetic-cli, which may not be checked out locally; if absent, cross-check defers to a brief/issue on eidetic-cli rather than blocking the release (task t4)
