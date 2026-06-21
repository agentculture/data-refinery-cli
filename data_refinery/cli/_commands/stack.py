"""``data-refinery stack`` — manage the storage substrate (mongo + neo4j).

The ``stack`` noun wraps ``docker compose`` over this repo's
``docker-compose.yml`` so the agent can manage the infrastructure it owns
(issue #1) without the operator hand-rolling compose invocations:

    data-refinery stack up        # docker compose up -d
    data-refinery stack down      # docker compose down
    data-refinery stack status    # docker compose ps (+ health)
    data-refinery stack status --json

Contract (agent-first):

* ``--json`` on every verb; results to stdout, diagnostics to stderr.
* Docker absent / compose missing / compose failure → :class:`CliError` with
  ``code=2`` (environment error) and a ``hint:`` — **never a Python traceback**.
* Exit ``0`` on success, ``2`` on an environment/setup problem.

``stack`` does not ship the database images; it orchestrates the upstream
``mongo:8.0`` + ``neo4j:5-community`` images referenced by the compose file.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess  # nosec B404 - used with a fixed argv, never shell=True
from pathlib import Path
from typing import Any

from data_refinery.cli._errors import EXIT_ENV_ERROR, CliError
from data_refinery.cli._output import emit_diagnostic, emit_result

_COMPOSE_FILENAME = "docker-compose.yml"
_DOCKER_HINT = (
    "install Docker and ensure 'docker compose' works (https://docs.docker.com/get-docker/)"
)
_COMPOSE_HINT = (
    "run from the data-refinery-cli repo (it ships docker-compose.yml), or pull "
    "the published stack: "
    "docker compose -f oci://ghcr.io/agentculture/data-refinery-stack:<tag> up -d"
)


def find_compose() -> Path | None:
    """Locate this repo's ``docker-compose.yml`` by walking up from this module.

    Mirrors :func:`data_refinery.cli._commands.whoami.find_culture_yaml`: the
    substrate definition is the agent's own, found relative to the installed
    package source — not whatever happens to sit in the caller's CWD. In a wheel
    install the compose file does not ship, so this returns ``None`` and the
    caller raises a structured environment error pointing at the published image.
    """
    here = Path(__file__).resolve()
    for parent in here.parents:
        candidate = parent / _COMPOSE_FILENAME
        if candidate.is_file():
            return candidate
    return None


def _require_docker() -> None:
    """Raise a structured environment error when docker is unavailable."""
    if shutil.which("docker") is None:
        raise CliError(
            code=EXIT_ENV_ERROR,
            message="docker is not installed or not on PATH",
            remediation=_DOCKER_HINT,
        )


def _require_compose() -> Path:
    compose = find_compose()
    if compose is None:
        raise CliError(
            code=EXIT_ENV_ERROR,
            message=f"could not locate {_COMPOSE_FILENAME} for the storage stack",
            remediation=_COMPOSE_HINT,
        )
    return compose


def _compose(compose: Path, *args: str) -> subprocess.CompletedProcess[str]:
    """Run ``docker compose -f <compose> <args...>`` capturing output.

    Never uses a shell; the argv is fixed. Translates a missing docker binary or
    a non-zero compose exit into a :class:`CliError` (code 2) so no traceback
    leaks.
    """
    cmd = ["docker", "compose", "-f", str(compose), *args]
    try:
        proc = subprocess.run(  # nosec B603 - fixed argv, no shell
            cmd,
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError as exc:  # docker vanished between check and run
        raise CliError(
            code=EXIT_ENV_ERROR,
            message="docker is not installed or not on PATH",
            remediation=_DOCKER_HINT,
        ) from exc
    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout or "").strip().splitlines()
        first = detail[0] if detail else f"exit code {proc.returncode}"
        verb = f" {args[0]}" if args else ""
        raise CliError(
            code=EXIT_ENV_ERROR,
            message=f"docker compose{verb} failed: {first}",
            remediation="check 'docker compose version' and that the docker daemon is running",
        )
    return proc


def _load_ps_rows(text: str) -> list[Any]:
    """Decode compose ps output: a top-level JSON array, else one object per line.

    Split out of :func:`_parse_ps` so the two-mode decoding (with its nested
    error handling) doesn't push that function's cognitive complexity over the
    limit. *text* is assumed already stripped and non-empty.
    """
    try:
        parsed = json.loads(text)
        return parsed if isinstance(parsed, list) else [parsed]
    except json.JSONDecodeError:
        pass
    rows: list[Any] = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return rows


def _parse_ps(stdout: str) -> list[dict[str, object]]:
    """Parse ``docker compose ps --format json`` (array OR one-object-per-line)."""
    text = stdout.strip()
    if not text:
        return []
    services: list[dict[str, object]] = []
    for row in _load_ps_rows(text):
        if not isinstance(row, dict):
            continue
        services.append(
            {
                "name": row.get("Name") or row.get("Service") or "?",
                "service": row.get("Service") or "?",
                "state": row.get("State") or "?",
                "health": row.get("Health") or "",
                "status": row.get("Status") or "",
            }
        )
    return services


def _status_payload(compose: Path) -> dict[str, object]:
    proc = _compose(compose, "ps", "--all", "--format", "json")
    services = _parse_ps(proc.stdout)
    running = [s for s in services if s["state"] == "running"]
    # A service is OK when it is running and not explicitly unhealthy/starting.
    # An empty health means "no healthcheck defined" (or not yet evaluated) —
    # treated as OK, but a reported "unhealthy"/"starting" is not.
    healthy = bool(services) and all(
        s["state"] == "running" and s["health"] not in ("unhealthy", "starting") for s in services
    )
    return {
        "compose_file": str(compose),
        "running": len(running) == len(services) and bool(services),
        "healthy": healthy,
        "services": services,
    }


def cmd_stack_up(args: argparse.Namespace) -> int:
    _require_docker()
    compose = _require_compose()
    json_mode = bool(getattr(args, "json", False))
    emit_diagnostic("bringing up the data-refinery storage stack (mongo + neo4j)…")
    # --wait blocks until services are healthy (or the timeout elapses), so the
    # status we report next is accurate and a consumer can connect immediately.
    _compose(compose, "up", "-d", "--wait", "--wait-timeout", "120")
    payload = _status_payload(compose)
    payload["command"] = "up"
    if json_mode:
        emit_result(payload, json_mode=True)
    else:
        names = ", ".join(str(s["name"]) for s in payload["services"]) or "(none)"
        emit_result(f"stack up: {names}", json_mode=False)
    return 0


def cmd_stack_down(args: argparse.Namespace) -> int:
    _require_docker()
    compose = _require_compose()
    json_mode = bool(getattr(args, "json", False))
    emit_diagnostic("stopping the data-refinery storage stack…")
    # --remove-orphans cleans up containers dropped from the compose file.
    _compose(compose, "down", "--remove-orphans")
    payload = {"command": "down", "compose_file": str(compose), "running": False}
    if json_mode:
        emit_result(payload, json_mode=True)
    else:
        emit_result("stack down: stopped", json_mode=False)
    return 0


def _render_status_text(payload: dict[str, object]) -> str:
    """Render the human-readable ``stack status`` text from a status payload."""
    services = payload["services"]
    if not services:
        return "stack status: no services running (try 'data-refinery stack up')"
    lines = [f"compose: {payload['compose_file']}", f"healthy: {payload['healthy']}"]
    for s in services:  # type: ignore[attr-defined]
        health = f" ({s['health']})" if s["health"] else ""
        lines.append(f"- {s['name']}: {s['state']}{health}")
    return "\n".join(lines)


def cmd_stack_status(args: argparse.Namespace) -> int:
    _require_docker()
    compose = _require_compose()
    json_mode = bool(getattr(args, "json", False))
    payload = _status_payload(compose)
    payload["command"] = "status"
    if json_mode:
        emit_result(payload, json_mode=True)
    else:
        emit_result(_render_status_text(payload), json_mode=False)
    return 0


def _stack_overview(args: argparse.Namespace) -> int:
    """`data-refinery stack` with no sub-verb prints the noun's overview."""
    from data_refinery.cli._commands.overview import emit_overview

    sections = [
        {
            "title": "Verbs",
            "items": [
                "stack up — bring up mongo (27018) + neo4j (7687) via docker compose",
                "stack down — stop the stack",
                "stack status — report per-service state + health",
            ],
        },
        {
            "title": "Substrate",
            "items": [
                "mongo:8.0 on host 27018 (mongodb://localhost:27018)",
                "neo4j:5-community on 7687 (bolt) + 7474 (ui), apoc, no auth",
                "defined in docker-compose.yml; published to GHCR as an OCI artifact",
            ],
        },
        {
            "title": "Conventions",
            "items": [
                "every verb supports --json",
                "docker absent / compose failure → exit 2 with a hint:, never a traceback",
            ],
        },
    ]
    emit_overview("data-refinery stack", sections, json_mode=bool(getattr(args, "json", False)))
    return 0


def _add_json_flag(p: argparse.ArgumentParser) -> None:
    p.add_argument("--json", action="store_true", help="Emit structured JSON.")


def register(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser(
        "stack",
        help="Manage the storage substrate (mongo + neo4j) via docker compose.",
    )
    _add_json_flag(p)
    p.set_defaults(func=_stack_overview, json=False)
    # Propagate the structured-error parser_class to nested verbs.
    verb = p.add_subparsers(dest="stack_command", parser_class=type(p))

    up = verb.add_parser("up", help="Bring the stack up (docker compose up -d).")
    _add_json_flag(up)
    up.set_defaults(func=cmd_stack_up)

    down = verb.add_parser("down", help="Stop the stack (docker compose down).")
    _add_json_flag(down)
    down.set_defaults(func=cmd_stack_down)

    status = verb.add_parser("status", help="Report per-service state + health.")
    _add_json_flag(status)
    status.set_defaults(func=cmd_stack_status)

    ov = verb.add_parser("overview", help="Describe the stack noun.")
    _add_json_flag(ov)
    ov.set_defaults(func=_stack_overview)
