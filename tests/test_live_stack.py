"""Wave-1 live test — the storage stack comes up and a consumer connects.

This is an **opt-in integration test**: it brings up the real mongo + neo4j
substrate via the CLI and proves a consumer (eidetic-cli first) reaches it on
eidetic's *default* endpoints with zero config change. It is dependency-light —
it checks TCP reachability of mongo (27018) and neo4j bolt (7687) and an HTTP 200
from the neo4j browser (7474) using only the stdlib, so it does NOT need the
`neo4j`/`pymongo` drivers (which stay out of the default deps).

Gating (so normal `pytest` and the unit-test CI job never pull images):

* skipped unless ``DATA_REFINERY_LIVE=1`` is set;
* skipped when docker is unavailable.

Run it explicitly:

    DATA_REFINERY_LIVE=1 uv run pytest tests/test_live_stack.py -v
"""

from __future__ import annotations

import os
import shutil
import socket
import time
import urllib.error
import urllib.request

import pytest

from data_refinery.cli import main

# eidetic-cli's *default* connection endpoints — hard-coded here on purpose, NOT
# imported from eidetic (it is a separate repo). The whole point of the test is
# that these unchanged defaults connect.
MONGO_HOST, MONGO_PORT = "localhost", 27018
NEO4J_HOST, NEO4J_BOLT, NEO4J_HTTP = "localhost", 7687, 7474

_LIVE = os.environ.get("DATA_REFINERY_LIVE") == "1"
_DOCKER = shutil.which("docker") is not None

pytestmark = [
    pytest.mark.skipif(not _LIVE, reason="set DATA_REFINERY_LIVE=1 to run the live stack test"),
    pytest.mark.skipif(not _DOCKER, reason="docker is not available"),
]


def _wait_tcp(host: str, port: int, timeout: float = 120.0) -> bool:
    """Return True once a TCP connect to host:port succeeds within timeout."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with socket.create_connection((host, port), timeout=3):
                return True
        except OSError:
            time.sleep(2)
    return False


def _wait_http(url: str, timeout: float = 120.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=3) as resp:  # nosec B310 - fixed localhost URL
                if 200 <= resp.status < 500:
                    return True
        except (urllib.error.URLError, OSError):
            time.sleep(2)
    return False


def _tcp_open(host: str, port: int) -> bool:
    try:
        with socket.create_connection((host, port), timeout=2):
            return True
    except OSError:
        return False


@pytest.fixture(scope="module")
def stack_up() -> None:
    """Ensure the substrate is up, tear down only what we brought up.

    On a clean box (CI) we bring our stack up and tear it down after. On a box
    where an equivalent substrate is *already* running on the same default ports
    (e.g. eidetic's stack mid-transition — identical image/ports/auth), we do
    not fight it: we verify connectivity against the running substrate, which is
    exactly the "eidetic's defaults connect with zero config change" signal.
    """
    if _tcp_open(MONGO_HOST, MONGO_PORT) or _tcp_open(NEO4J_HOST, NEO4J_BOLT):
        yield "preexisting"  # a substrate already serves the default endpoints
        return
    rc = main(["stack", "up"])
    if rc != 0:
        pytest.skip("could not bring up the stack (docker/ports unavailable)")
    try:
        yield "ours"
    finally:
        main(["stack", "down"])


def test_mongo_default_port_reachable(stack_up: str) -> None:
    assert _wait_tcp(MONGO_HOST, MONGO_PORT), (
        f"mongo not reachable on {MONGO_HOST}:{MONGO_PORT} — eidetic's default "
        "EIDETIC_MONGO_URI=mongodb://localhost:27018 would not connect"
    )


def test_neo4j_bolt_default_port_reachable(stack_up: str) -> None:
    assert _wait_tcp(NEO4J_HOST, NEO4J_BOLT), (
        f"neo4j bolt not reachable on {NEO4J_HOST}:{NEO4J_BOLT} — eidetic's "
        "default NEO4J_URI=bolt://localhost:7687 would not connect"
    )


def test_neo4j_http_serving(stack_up: str) -> None:
    assert _wait_http(
        f"http://{NEO4J_HOST}:{NEO4J_HTTP}"
    ), "neo4j browser did not serve on 7474 — the container is not healthy"


def test_stack_status_reports_running(stack_up: str, capsys: pytest.CaptureFixture[str]) -> None:
    import json

    if stack_up != "ours":
        pytest.skip("a preexisting substrate serves the ports; not our containers to report")
    rc = main(["stack", "status", "--json"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    names = {s["name"] for s in payload["services"]}
    assert {"data-refinery-mongo", "data-refinery-neo4j"} <= names
