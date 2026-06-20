# data-refinery-cli ships the storage + data-quality infra layer split out of eidetic-cli: a docker stack (mongo 27018 + neo4j 7687) published as a multi-arch GHCR image, files/cypher/mongo store adapters, and a consumer-agnostic data-quality CLI surface (validate, dedup, integrity, freshness) that eidetic consumes over a subprocess boundary as its first consumer

> data-refinery-cli ships the storage + data-quality infra layer split out of eidetic-cli: a docker stack (mongo 27018 + neo4j 7687) published as a multi-arch GHCR image, files/cypher/mongo store adapters, and a consumer-agnostic data-quality CLI surface (validate, dedup, integrity, freshness) that eidetic consumes over a subprocess boundary as its first consumer

## Audience

- eidetic-cli (first consumer, over a subprocess-not-import boundary) and any future agent needing a dependency-light data store + quality checks; plus the data-refinery-cli mesh agent operator

## Before → After

- Before: the storage/quality substrate lives in eidetic-cli (neo4j+pymongo deps, its own docker-compose, store/cypher adapters) — but data-refinery-cli's README already promises to own it and the code was originally cited FROM data-refinery; today data-refinery-cli has dependencies=[] and only the introspection scaffold
- After: data-refinery-cli owns the docker stack (GHCR image) + the store adapters + a consumer-agnostic data-quality CLI; eidetic pulls the image and (phase 2) calls the CLI over a process boundary, dropping its own DB drivers

## Why it matters

- the storage + data-quality layer is reusable beyond agent-memory; returning it to its origin makes data-refinery-cli the canonical owner instead of a cited-from reference, and unblocks eidetic to be a thin agentic-memory layer

## Requirements

- docker-compose.yml brings up mongo:8.0 (host 27018->27017) + neo4j:5-community (7687 bolt, 7474 ui, apoc, NEO4J_AUTH=none) with healthchecks + volumes, matching eidetic's ports/auth so eidetic connects with no config change; container names data-refinery-*
  - honesty: starting the compose yields mongo reachable on localhost:27018 and neo4j on bolt://localhost:7687 with apoc; eidetic's existing default env connects with zero config change
- A multi-arch (amd64+arm64) image published to GHCR on tag/release that brings up the mongo+neo4j substrate, so a consumer docker-pulls instead of hand-rolling compose; image name + tag scheme documented for pinning
  - honesty: a consumer on amd64 OR arm64 docker-pulls a tagged image and brings up the same substrate; the tag scheme is documented and immutable per release
- A stack-management CLI (e.g. data-refinery stack up/down/status) wrapping the compose/image so the agent manages the infra it owns; --json status, no traceback, structured errors
  - honesty: data-refinery stack up/down/status manages the substrate and status --json reports health with no traceback when docker is absent (CliError code 2 + hint)
- Files + cypher(neo4j) + mongo store adapters behind a backend Protocol (upsert/get/list/all + scope-filtered fetch), returned from eidetic, with neo4j+pymongo behind an optional extra [store], lazy-imported in function bodies, CliError(code=2)+install hint when absent; dependencies=[] stays the default and a static test asserts no top-level optional import
  - honesty: with dependencies=[] installed, non-store verbs work; a store verb without the [store] extra exits code 2 with an install hint; a static test asserts neo4j/pymongo are never imported at module top level
- A consumer-agnostic data-quality CLI surface: validate (envelope shape), dedup (by id/hash, idempotent upsert — never duplicate), integrity (hash matches content / referential checks), freshness (age/staleness facts) — all JSON in/out, no eidetic memory semantics
  - honesty: dedup is idempotent: running it twice over the same input yields identical store state and never creates a duplicate by id or hash; validate/integrity/freshness return structured JSON facts
- public/private scope no-leak survives the boundary: a private-scope document is never reachable via a public-scope fetch (can_serve preserved at the storage layer); this is enforced by data-refinery, not just eidetic
  - honesty: a test stores a private-scope document and proves a public-scope fetch can never return it, across every backend adapter
- Full agent-first CLI contract on every new verb: --json everywhere, strict stdout(result)/stderr(error) split, hint: on errors, documented exit codes (0/1/2/3+), no Python traceback ever (CliError + dispatcher wrap)
  - honesty: teken cli doctor . --strict passes for every new verb: --json present, no traceback, hint: on errors, documented exit codes
- The package is importable as a library in addition to the subprocess CLI: a stable public Python API (e.g. data_refinery.store, data_refinery.quality) so a consumer can import OR shell out; both surfaces share one implementation
  - honesty: import data_refinery; data_refinery.store.put(...) works as a library AND data-refinery store put behaves identically over one shared implementation; both surfaces are tested
- A versioned, documented contract eidetic can pin: the CLI verbs + JSON shapes AND the image name/tag scheme, with semver discipline; documented in repo (docs/) so eidetic pins a known surface
  - honesty: the documented contract carries a version eidetic can reference, and changing a JSON shape or image tag requires a semver bump

## Honesty conditions

- eidetic adopts data-refinery's stack + boundary with no regression to remember/recall, and the split is documented well enough that eidetic pins a known version
- eidetic consumes the layer over a process boundary, and the surface is generic enough that a non-memory consumer could use store+quality without inheriting any memory concepts
- verifiable today: data-refinery-cli has dependencies=[] and no compose/store code, while eidetic owns neo4j+pymongo+its own compose
- after the split data-refinery-cli's repo contains the compose + GHCR workflow + (later) store/quality surface, and eidetic can point at them with a pinned version
- the storage+quality layer is demonstrably reusable beyond agent-memory (a non-eidetic consumer shape is expressible) and eidetic becomes thinner
- each wave is independently landable: wave 1 (stack + GHCR + stack CLI) ships and is usable by eidetic before wave 2 exists
- a live test shows eidetic's default env connecting to the data-refinery stack with zero config change; dedup idempotency + scope no-leak hold across the boundary

## Success signals

- eidetic, unchanged, docker-pulls the GHCR image and its existing 27018/7687 defaults connect; then (phase 2) eidetic stores+fetches through data-refinery's CLI/library over a process boundary and can drop neo4j+pymongo from its own runtime deps; idempotent dedup + scope no-leak hold across the boundary

## Scope / boundaries

- Phased: wave 1 ships the docker stack + a stack-management CLI + the GHCR image; wave 2 ships the generic store adapters + consumer-agnostic data-quality CLI; wave 3 ships the pinnable contract + eidetic consumption. data-refinery stores OPAQUE documents and never interprets them as memories

## Non-goals

- data-refinery does NOT own relevance ranking, the freshness *signal* (ranking blend), lifecycle (shadow/archive/no-hard-delete), or the memory record schema with temporal fields — those stay in eidetic. It exposes freshness as a *check* (age/staleness facts), not a ranking signal
- Not a new clonable template, and not a reimplementation of the autonomous-intelligence/data-refinery extraction pipeline (pdf->entities). The introspection scaffold stays only as the agent-first CLI contract host

## Assumptions

- model-gear embeddings/rerank stay external to data-refinery (HTTP, with the dep-free local lexical fallback carried over). Raw vector storage = opaque blob attached to a document if needed; vector indexing/ANN is deferred past the initial waves

## Decisions

- data-refinery defines a GENERIC storage envelope {id, hash, content, scope{name,visibility}, metadata} — the storage-neutral subset of eidetic's Record. eidetic's memory-specific fields (lifecycle/signal/recall_count/supersedes/links/created) ride inside metadata or stay eidetic's concern; data-refinery never depends on them
- GHCR deliverable = the versioned docker-compose published as an OCI artifact (docker compose publish) referencing upstream mongo:8.0 + neo4j:5-community (multi-arch for free); a 'data-refinery stack up/down/status' CLI wraps pull+run. No fat single-DB image.
- Scope of THIS effort = Wave 1 only (docker-compose + GHCR publish workflow + stack CLI + image/tag docs), landed as one PR. Wave 2 (envelope + store adapters + data-quality verbs) and Wave 3 (pinnable contract + eidetic consumption) are tracked as follow-up issues via /communicate, not built now.

## Open / follow-up

- raw vector storage / ANN indexing ownership + timing — opaque-blob now vs a real vector index later; revisit once a consumer needs semantic search THROUGH data-refinery rather than eidetic
