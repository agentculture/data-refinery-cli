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

These ports and auth match eidetic-cli's historical defaults, so a consumer
connects with **zero config change**.

> **Security — loopback by default.** neo4j runs with `NEO4J_AUTH=none` and mongo
> has no auth, so the ports bind to **`127.0.0.1` only** by default — the
> unauthenticated databases are not reachable from other hosts. A same-host
> consumer (`mongodb://localhost:27018`, `bolt://localhost:7687`) is unaffected.
> To expose on all interfaces (only on a trusted/isolated network), set
> `DR_BIND=0.0.0.0` (e.g. `DR_BIND=0.0.0.0 data-refinery stack up`).

The compose **project name is `data-refinery-stack`** (not `data-refinery`) to
avoid colliding with the sibling `autonomous-intelligence/data-refinery` compose
project.

## Image name and tag scheme

- **Name:** `ghcr.io/agentculture/data-refinery-stack`
- **Tags:** the release version without the leading `v` (e.g. `0.4.0`), plus
  `latest`.
- **Immutability:** a given version tag is published exactly once. Treat
  `0.4.0` as immutable; `latest` floats.
- **Cadence:** the image is **only (re)published when `docker-compose.yml`
  actually changes** between releases — most releases bump the CLI, not the
  substrate, so the stack image stays put while the PyPI version moves. The
  image version therefore tracks the latest release in which the compose
  changed, not every release.

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
data-refinery stack up        # docker compose up -d --wait
data-refinery stack status    # per-service state + health
data-refinery stack down
```

> `stack up` uses `docker compose up --wait` (waits until healthy) — needs Docker
> Compose ≥ 2.20. On older Compose, run `docker compose up -d` directly.

## Reproducibility

The compose pins image **tags** (`mongo:8.0`, `neo4j:5-community`), matching
eidetic's defaults rather than pinning digests. Tags are mutable upstream; a
consumer that needs byte-for-byte reproducibility should pin the upstream image
**digests** in its own copy of the compose file.

## Publishing

[`.github/workflows/publish-stack.yml`](../.github/workflows/publish-stack.yml)
runs on every **push to `main`** (a merged PR). Its `tag` job derives the version
from `pyproject.toml` and creates the `v<version>` git tag (so tags track the
PyPI release 1:1), then gates: it only proceeds to publish when `docker-compose.yml`
differs from the previous tag. When it does, the `publish-stack` job validates the
compose, logs in to GHCR with the workflow token, `docker compose publish`es the
OCI artifact at the version tag and `latest`, and attaches `docker-compose.yml` to
the release. A `workflow_dispatch` with a `tag` input force-(re)publishes a
specific version's stack regardless of the gate.
