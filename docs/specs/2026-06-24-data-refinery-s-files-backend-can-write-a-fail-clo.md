# data-refinery's files backend can write a fail-closed .gitignore on store-dir materialization, so a consumer keeps private shards out of git without ever constructing a write path itself

> data-refinery's files backend can write a fail-closed .gitignore on store-dir materialization, so a consumer keeps private shards out of git without ever constructing a write path itself

## Audience

- eidetic-cli (the first consumer, moving to repo-contained memory) and the assisting agent; more generally any files-backend consumer that wants repo-contained private shards

## Before → After

- Before: a consumer that wants private shards out of git must construct and write a .gitignore itself, reintroducing exactly the pythonsecurity:S2083 write-path sink that #8 removed by moving path-construction to DR
- After: a files store dir is materialized with a fail-closed .gitignore that ignores everything but public shards, so private shards (`<scope>__private.jsonl`) are git-ignored from their first write; the consumer opts in with a single flag and never builds a write path

## Why it matters

- DR owns the `<scope>__<visibility>.jsonl` on-disk layout, so DR must own the ignore pattern that tracks it; a whitelist (fail-closed) excludes any future private filename or sidecar DR introduces by default rather than silently leaking it

## Requirements

- expose an opt-in write_gitignore flag (default False) on FilesBackend init, plumbed through the store surface eidetic consumes so the consumer passes only a bool and a base_dir it already owns
  - honesty: with the flag OFF (the default), a materialized store dir is byte-for-byte identical to today: no .gitignore, no extra files, no behavior change on any existing consumer or dir
- when on, ensure base_dir/.gitignore holds the fail-closed whitelist exactly: a line '*', then '!.gitignore', then '!*__public.jsonl' — created only on a write/materialize, never on a read
  - honesty: in a real git repo, git check-ignore confirms `<scope>__private.jsonl` is ignored AND `<scope>__public.jsonl` is tracked under an opted-in base_dir
  - honesty: a read-only get()/list() (and a dry-run migrate) never creates the .gitignore; only an actual write/materialize does

## Honesty conditions

- a files store dir opted in to write_gitignore ends up with private shards untracked by git and public shards tracked, and the consumer supplied only a bool + a base_dir it owns (no write path)
- eidetic-cli is a real, named first consumer whose repo-contained-memory cutover (its 2026-06-24 spec) is blocked on this issue, and the surface is generic enough that any other files-backend consumer could opt in identically
- the consumer reaches the materialized .gitignore by passing only write_gitignore=True + a base_dir it already owns; a test drives store.put/migrate and asserts the file exists without the caller building any path
- without this endpoint the consumer's own .gitignore write is a flagged pythonsecurity:S2083 path sink (eidetic's prior BLOCKER that #8 and this issue move to DR)
- because the whitelist allows only *__public.jsonl, an arbitrary non-public sidecar name DR might add later is git-ignored by default — verifiable with git check-ignore on a made-up sidecar filename
- mongo/neo4j is a no-op (no .gitignore), a read get()/list() creates nothing, and an existing .gitignore is never rewritten — each is a distinct passing test
- the acceptance trio (check-ignore private-ignored & public-tracked; idempotent re-run writes nothing; OFF is byte-identical) are all expressible as passing tests, and the change ships under a bumped version + CHANGELOG entry
- re-materializing when a .gitignore already exists writes nothing and never overwrites it, even if its content differs from the canonical whitelist
- eidetic can reach write_gitignore through the importable store surface it already uses (store.migrate / store.put), so it never constructs a filesystem write path — confirming this requires checking eidetic's actual consumption call

## Success signals

- in an opted-in dir, git check-ignore reports `<scope>__private.jsonl` ignored and `<scope>__public.jsonl` tracked; re-materializing writes nothing (idempotent); option OFF is byte-identical to today; shipped in a tagged release eidetic can pin a floor to

## Scope / boundaries

- files backend only (mongo/neo4j have no on-disk dir -> no-op); never write on a read (list()/get() must not create files); never clobber an existing .gitignore; default OFF so existing dirs stay byte-identical

## Assumptions

- eidetic consumes write_gitignore via the importable store surface (store.migrate and/or store.put with base_dir + write_gitignore), which requires fixing files.build to stop dropping kwargs; no new CLI flag is needed for v1

## Decisions

- create-when-absent only: if any .gitignore already exists, do nothing (no rewrite, no clobber) — it may carry user edits; idempotency is existence-based, not content-match
