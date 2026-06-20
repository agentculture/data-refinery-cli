# Build Plan — data-refinery-cli ships the storage + data-quality infra layer split out of eidetic-cli: a docker stack (mongo 27018 + neo4j 7687) published as a multi-arch GHCR image, files/cypher/mongo store adapters, and a consumer-agnostic data-quality CLI surface (validate, dedup, integrity, freshness) that eidetic consumes over a subprocess boundary as its first consumer

slug: `data-refinery-cli-ships-the-storage-data-quality-i` · status: `exported` · from frame: `data-refinery-cli-ships-the-storage-data-quality-i`

> data-refinery-cli ships the storage + data-quality infra layer split out of eidetic-cli: a docker stack (mongo 27018 + neo4j 7687) published as a multi-arch GHCR image, files/cypher/mongo store adapters, and a consumer-agnostic data-quality CLI surface (validate, dedup, integrity, freshness) that eidetic consumes over a subprocess boundary as its first consumer

## Tasks

### t1 — Author docker-compose.yml for the mongo+neo4j substrate

- covers: c9, h2
- acceptance:
  - docker compose up -d brings mongo on host 27018->27017 and neo4j on 7687(bolt)+7474(ui) with NEO4J_PLUGINS=[apoc] and NEO4J_AUTH=none; both healthchecks report healthy; containers named data-refinery-mongo/data-refinery-neo4j; named volumes persist data
  - eidetic's default env (mongodb://localhost:27018, bolt://localhost:7687) connects with zero config change

### t2 — Add the stack CLI verb (up/down/status) wrapping compose

- depends on: t1
- covers: c11, h4
- acceptance:
  - data-refinery stack up|down|status manage the substrate via docker compose; stack status --json emits structured per-service health on stdout
  - when docker is absent the verb exits code 2 with a hint: on stderr and NO Python traceback; explain/catalog + overview entries added for the stack noun

### t3 — GHCR publish workflow: compose as versioned multi-arch OCI artifact

- depends on: t1
- covers: c10, h3
- acceptance:
  - on tag/release a workflow runs docker compose publish to ghcr.io/agentculture/<name>:<tag>; the OCI artifact references upstream multi-arch mongo:8.0 + neo4j:5-community (no fat single-DB image)
  - docs/stack-image.md documents the image name + immutable-per-release tag scheme a consumer pins

### t4 — Agent-first contract conformance + tests for the stack verb

- depends on: t2
- covers: c15, h8
- acceptance:
  - teken cli doctor . --strict passes; pytest covers stack up/down/status happy paths + the docker-absent code-2 path; --json present, strict stdout/stderr split, hint: on error, exit codes documented

### t5 — Versioned contract doc eidetic can pin (wave-1 surface)

- depends on: t3
- covers: c17, h10
- acceptance:
  - docs/contract.md states a contract version string, the image name/tag scheme, and the rule that changing a JSON shape or image tag requires a semver bump; wave-2 verb JSON shapes are stubbed as 'added in wave 2'

### t6 — Docs/identity alignment to the split (README/CLAUDE/AGENTS)

- covers: c1, h1, c2, h11, c3, h12, c4, h13, c5, h14, c6, h15
- acceptance:
  - README/CLAUDE/AGENTS.colleague.md describe the split honestly: audience (eidetic + future non-memory consumers), before/after state, why (reusable beyond memory), the phased wave boundaries (wave 1 landable alone), and that data-refinery stores OPAQUE documents (no memory semantics)

### t7 — Wave-1 live test: eidetic connects to the stack unchanged

- depends on: t1, t2
- covers: c18, h16
- acceptance:
  - a docker-gated check brings the stack up and shows eidetic's default env connecting + a store/fetch round-trip; the check is skipped (not failed) when docker is unavailable; dedup idempotency + scope no-leak are recorded as wave-2 verification items

### t8 — Version bump + changelog for the Wave 1 PR

- depends on: t4, t5, t6
- acceptance:
  - pyproject.toml version bumped via the version-bump skill; CHANGELOG.md gets a Keep-a-Changelog entry; version-check CI passes against origin/main

### t9 — [wave2] Generic storage envelope + importable store API

- covers: c16, h9
- acceptance:
  - data_refinery.store.put/get/list operate on a generic envelope {id,hash,content,scope{name,visibility},metadata} with NO memory fields; data-refinery store put/get mirror the library over one shared implementation; both surfaces tested

### t10 — [wave2] Store adapters (files/neo4j/mongo) behind a Protocol + optional [store] extra

- depends on: t9
- covers: c12, h5
- acceptance:
  - backend Protocol upsert/get/list/all; neo4j+pymongo only under the [store] optional-dependencies extra, lazy-imported in function bodies; a store verb without the extra exits code 2 with an install hint; a static test asserts neo4j/pymongo are never imported at module top level; dependencies=[] default unchanged

### t11 — [wave2] Data-quality verbs: validate/dedup/integrity/freshness

- depends on: t9, t10
- covers: c13, h6
- acceptance:
  - dedup is idempotent by id/hash (running twice over the same input yields identical store state, never a duplicate); validate (envelope shape), integrity (hash matches content), freshness (age/staleness facts) each return structured JSON; all verbs --json, no traceback

### t12 — [wave2] Scope no-leak enforcement across all backends

- depends on: t10
- covers: c14, h7
- acceptance:
  - can_serve(query_scope, record_scope) preserved at the storage layer; a test stores a private-scope document and proves a public-scope fetch can never return it, across files/neo4j/mongo adapters

## Risks

- [follow_up] Wave 2 (envelope + adapters + data-quality verbs, tasks t9-t12) and Wave 3 (full pinnable verb-JSON contract + eidetic consumption over the process boundary) are deliberately NOT built in this effort; tracked as follow-up issues via /communicate
- [unknown_nonblocking] GHCR 'docker compose publish' OCI-artifact support: verify the runner's docker/compose version supports publishing a compose file as an OCI artifact, and that consumers can run from oci://; fall back to publishing the compose as a release asset if unsupported
- [follow_up] raw vector storage / ANN indexing ownership + timing — opaque-blob now vs a real vector index later; revisit once a consumer needs semantic search THROUGH data-refinery
