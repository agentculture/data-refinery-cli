# The data-refinery storage stack image

data-refinery-cli owns the storage substrate for the AgentCulture mesh (issue
[#1](https://github.com/agentculture/data-refinery-cli/issues/1)) and publishes
it so a consumer (eidetic-cli first) can pull it instead of hand-rolling compose.

## What is published

The substrate is two upstream services, defined in
[`docker-compose.yml`](../docker-compose.yml) at the repo root:

| Service | Image | Host port | Notes |
|---------|-------|-----------|-------|
| `data-refinery-mongo` | `mongo:8.0` | **27018** → 27017 | `27018`, **not** 27017 — deliberate collision-avoidance |
| `data-refinery-neo4j` | `neo4j:5-community` | **7687** (bolt), **7474** (UI) | `apoc`, `NEO4J_AUTH=none` |

These ports and auth match eidetic-cli's historical defaults exactly, so a
consumer connects with **zero config change**.

The compose **project name is `data-refinery-stack`** (not `data-refinery`) to
avoid colliding with the sibling `autonomous-intelligence/data-refinery` compose
project.

## Image name and tag scheme

- **Name:** `ghcr.io/agentculture/data-refinery-stack`
- **Tags:** the release version without the leading `v` (e.g. `0.4.0`), plus
  `latest`.
- **Immutability:** a given version tag is published exactly once, on the
  `v<version>` git tag. Treat `0.4.0` as immutable; `latest` floats.

> **Not a multi-arch image.** The published artifact is a single OCI manifest
> produced by `docker compose publish` — it *references* the upstream `mongo:8.0`
> and `neo4j:5-community` images, which are themselves multi-arch. A consumer on
> amd64 or arm64 resolves the correct platform of those upstream images at pull
> time. There is no custom image built here.

## How a consumer brings it up

**Path 1 — OCI artifact (preferred, needs Docker Compose v2.24+):**

```bash
docker compose -f oci://ghcr.io/agentculture/data-refinery-stack:0.4.0 up -d
```

**Path 2 — release asset (portable fallback):** the same `docker-compose.yml` is
attached to each GitHub Release. Older docker/compose can use it directly:

```bash
curl -fsSL -o data-refinery-stack.yml \
  https://github.com/agentculture/data-refinery-cli/releases/download/v0.4.0/docker-compose.yml
docker compose -f data-refinery-stack.yml up -d
```

**Path 3 — from this repo:** the agent that owns the stack manages it with its
own CLI, which wraps the in-repo compose file:

```bash
data-refinery stack up        # docker compose up -d
data-refinery stack status    # per-service state + health
data-refinery stack down
```

## Reproducibility

The compose pins image **tags** (`mongo:8.0`, `neo4j:5-community`), matching
eidetic's defaults rather than pinning digests. Tags are mutable upstream; a
consumer that needs byte-for-byte reproducibility should pin the upstream image
**digests** in its own copy of the compose file.

## Publishing

[`.github/workflows/publish-stack.yml`](../.github/workflows/publish-stack.yml)
runs on a `v*` tag (or `workflow_dispatch`): it validates the compose, logs in to
GHCR with the workflow token, `docker compose publish`es the OCI artifact at the
version tag and `latest`, and attaches `docker-compose.yml` to the release.
