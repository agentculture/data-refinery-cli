# data-refinery now owns store-file migration: a consumer upgrades an on-disk store to the current Envelope format by supplying only a transform, never constructing a filesystem write path — files granularity first

> data-refinery now owns store-file migration: a consumer upgrades an on-disk store to the current Envelope format by supplying only a transform, never constructing a filesystem write path — files granularity first

## Audience

- eidetic-cli (first consumer over the import + subprocess boundary) and any future consumer of data-refinery's store boundary

## Before → After

- Before: eidetic's migrate_store.py globs the operator-supplied store dir, writes *.jsonl.tmp then os.replace; SonarCloud flags that consumer-side write sink as pythonsecurity:S2083 BLOCKER, which is structurally unsatisfiable for a local CLI and fails eidetic's gate
- After: a consumer upgrades a populated legacy on-disk store to the current Envelope-JSONL format by calling data_refinery.store.migrate(transform) (import) or 'data-refinery store migrate' (subprocess), supplying only a transform/target format — data-refinery resolves the store root and owns the atomic per-file rewrite

## Why it matters

- the path-construction concern (and the S2083 sink) belongs to the component that OWNS the storage layout; moving it behind data-refinery's boundary lets eidetic delete migrate_store.py and go green without any in-repo rule suppression

## Requirements

- the rewrite is atomic per file (tmp sibling in the same dir + os.replace) and idempotent (a file already in target format is left byte-identical; a re-run converts nothing)
  - honesty: running migrate twice over the same store yields a byte-identical store on the second run, and killing the process mid-rewrite leaves either the old or the new file intact (never a partial/truncated file), because os.replace is atomic on POSIX
- data-refinery resolves and validates the store root internally (canonicalize via os.path.realpath + containment-check via os.path.commonpath against an owner-controlled root); the consumer supplies a root directory or a transform, never a constructed per-file write path
  - honesty: a migrate call whose resolved per-file path escapes the canonicalized store root (e.g. via a symlink) is refused with a structured code-2 CliError, and Sonar's S2083 taint is satisfiable here because the sink reasons against an owner-canonicalized root rather than a raw consumer arg
- every transformed line is validated against the Envelope shape and the public/private scope no-leak (can_serve) before being written; an unparseable/invalid legacy line fails the migration with a structured CliError, never a traceback
  - honesty: a legacy line that does not transform into a valid Envelope (bad shape, or an unrecognised scope.visibility) aborts the file's migration before any os.replace, leaving the original file untouched, and emits error:/hint: on stderr with no traceback

## Honesty conditions

- the endpoint ships BOTH importable (store.migrate) and as a CLI verb (store migrate), both documented in the pinnable contract.md with a version bump
- eidetic can reach the endpoint over BOTH the import boundary (callable transform) and the subprocess boundary (self-canonicalize); no third component is needed
- in the eidetic call site, the only argument eidetic supplies is a transform callable (and optionally the store root it already owns) — never a constructed per-file *.jsonl.tmp path
- the S2083 BLOCKER is on eidetic's write sink in migrate_store.py and is unsatisfiable there because writing into the operator's chosen dir IS the feature
- after the cutover eidetic's gate clears with zero in-repo suppression (no # NOSONAR, no sonar exclusion entry for migrate_store.py)
- all four issue-#8 acceptance criteria are demonstrably met by a live test: upgrade-without-path, idempotent, atomic-per-file, eidetic deletes the module
- mongo/neo4j migration get a clean extension seam (a backend-level hook) but only the files backend actually rewrites now; data-refinery never imports eidetic's Record schema

## Success signals

- eidetic deletes migrate_store.py + its tests and replaces 'eidetic migrate store' with a thin call into data-refinery; eidetic's S2083 BLOCKER disappears and its gate goes green with no rule suppression; re-running migrate converts nothing (idempotent); an interrupted run is safe to resume (atomic per file)

## Scope / boundaries

- no eidetic Record/memory semantics leak into data-refinery; files backend granularity FIRST (mongo/vectors then neo4j/graph are later granularities); not a general ETL framework

## Decisions

- the importable store.migrate(transform) takes a Python callable Callable[[dict], Envelope|None]; the 'data-refinery store migrate' CLI verb canNOT cross a callable over argv, so it only re-canonicalizes data-refinery's OWN Envelope-JSONL (re-validate + re-fill hash + atomic rewrite) — a self-heal/format-version bump, never a consumer transform
