"""Tests for the ``data-refinery stack`` verb.

Docker is mocked throughout so these run with no daemon. The load-bearing
contract checks: ``--json`` shapes, the strict stdout/stderr split, and that an
absent/failing docker yields exit code 2 with a ``hint:`` and **no traceback**.
"""

from __future__ import annotations

import json
import subprocess

import pytest

from data_refinery.cli import main
from data_refinery.cli._commands import stack

_PS_RUNNING = json.dumps(
    [
        {
            "Name": "data-refinery-mongo",
            "Service": "data-refinery-mongo",
            "State": "running",
            "Health": "healthy",
            "Status": "Up 2 minutes",
        },
        {
            "Name": "data-refinery-neo4j",
            "Service": "data-refinery-neo4j",
            "State": "running",
            "Health": "healthy",
            "Status": "Up 2 minutes",
        },
    ]
)


def _fake_run_ok(cmd, capture_output=False, text=False, check=False):  # noqa: ANN001
    """Stand in for subprocess.run: ps returns two healthy services."""
    stdout = _PS_RUNNING if "ps" in cmd else ""
    return subprocess.CompletedProcess(cmd, 0, stdout=stdout, stderr="")


def _fake_run_fail(cmd, capture_output=False, text=False, check=False):  # noqa: ANN001
    return subprocess.CompletedProcess(
        cmd, 1, stdout="", stderr="Cannot connect to the Docker daemon"
    )


@pytest.fixture
def docker_present(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(stack.shutil, "which", lambda _name: "/usr/bin/docker")


# --- overview / explain (no docker needed) --------------------------------


def test_stack_no_verb_prints_overview(capsys: pytest.CaptureFixture[str]) -> None:
    rc = main(["stack"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "# data-refinery stack" in out
    assert "27018" in out


def test_stack_overview_json(capsys: pytest.CaptureFixture[str]) -> None:
    rc = main(["stack", "--json"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["subject"] == "data-refinery stack"
    assert any(s["title"] == "Substrate" for s in payload["sections"])


def test_explain_stack_resolves(capsys: pytest.CaptureFixture[str]) -> None:
    rc = main(["explain", "stack"])
    assert rc == 0
    assert capsys.readouterr().out.startswith("# data-refinery stack")


# --- status / up / down (docker mocked) -----------------------------------


def test_stack_status_json(
    docker_present: None, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(stack.subprocess, "run", _fake_run_ok)
    rc = main(["stack", "status", "--json"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["command"] == "status"
    assert payload["healthy"] is True
    assert {s["name"] for s in payload["services"]} == {
        "data-refinery-mongo",
        "data-refinery-neo4j",
    }


def test_stack_status_text(
    docker_present: None, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(stack.subprocess, "run", _fake_run_ok)
    rc = main(["stack", "status"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "data-refinery-mongo: running (healthy)" in out


def test_stack_up(
    docker_present: None, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(stack.subprocess, "run", _fake_run_ok)
    rc = main(["stack", "up", "--json"])
    assert rc == 0
    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert payload["command"] == "up"
    # diagnostics go to stderr, never mixed into the JSON result on stdout
    assert "bringing up" in captured.err


def test_stack_down(
    docker_present: None, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(stack.subprocess, "run", _fake_run_ok)
    rc = main(["stack", "down", "--json"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["command"] == "down"
    assert payload["running"] is False


# --- environment-error paths (the no-traceback contract) ------------------


def test_docker_absent_exits_2_with_hint(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(stack.shutil, "which", lambda _name: None)
    rc = main(["stack", "status"])
    assert rc == 2
    err = capsys.readouterr().err
    assert err.startswith("error:")
    assert "hint:" in err
    assert "Traceback" not in err


def test_docker_absent_json(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(stack.shutil, "which", lambda _name: None)
    rc = main(["stack", "up", "--json"])
    assert rc == 2
    payload = json.loads(capsys.readouterr().err)
    assert payload["code"] == 2
    assert payload["remediation"]


def test_compose_missing_exits_2(
    docker_present: None, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(stack, "find_compose", lambda: None)
    rc = main(["stack", "status"])
    assert rc == 2
    err = capsys.readouterr().err
    assert "hint:" in err
    assert "Traceback" not in err


def test_compose_failure_exits_2(
    docker_present: None, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(stack.subprocess, "run", _fake_run_fail)
    rc = main(["stack", "status"])
    assert rc == 2
    err = capsys.readouterr().err
    assert err.startswith("error:")
    assert "Docker daemon" in err
    assert "Traceback" not in err


def test_docker_vanishes_midrun_exits_2(
    docker_present: None, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def _raise(*_a, **_k):  # noqa: ANN002, ANN003
        raise FileNotFoundError("docker")

    monkeypatch.setattr(stack.subprocess, "run", _raise)
    rc = main(["stack", "status"])
    assert rc == 2
    assert "hint:" in capsys.readouterr().err


# --- _parse_ps robustness -------------------------------------------------


def test_parse_ps_line_delimited() -> None:
    text = "\n".join(
        [
            json.dumps({"Name": "a", "Service": "a", "State": "running", "Health": "healthy"}),
            json.dumps({"Name": "b", "Service": "b", "State": "exited", "Health": ""}),
        ]
    )
    services = stack._parse_ps(text)
    assert [s["name"] for s in services] == ["a", "b"]


def test_parse_ps_empty() -> None:
    assert stack._parse_ps("") == []
    assert stack._parse_ps("   \n  ") == []
