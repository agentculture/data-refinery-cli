"""Markdown catalog for ``data-refinery-cli explain <path>``.

Each entry is verbatim markdown. Keys are command-path tuples. The empty tuple
and ``("data-refinery-cli",)`` both resolve to the root entry.

Keep bodies self-contained: an agent reading one entry should get enough
context without chaining reads.
"""

from __future__ import annotations

_ROOT = """\
# data-refinery-cli

A clonable template for AgentCulture mesh agents. It carries an agent-first CLI
(cited from the teken `python-cli` reference), a mesh identity (`culture.yaml` +
`CLAUDE.md`), the canonical guildmaster skill kit under `.claude/skills/`, and a
buildable/deployable package baseline. Clone it, rename the package, edit
`culture.yaml`, and you have a new agent.

## Verbs

- `data-refinery-cli whoami` — identity probe from `culture.yaml`.
- `data-refinery-cli learn` — structured self-teaching prompt.
- `data-refinery-cli explain <path>` — markdown docs for any noun/verb.
- `data-refinery-cli overview` — descriptive snapshot of the agent.
- `data-refinery-cli doctor` — check the agent-identity invariants.
- `data-refinery-cli cli overview` — describe the CLI surface.

## Exit-code policy

- `0` success
- `1` user-input error
- `2` environment / setup error
- `3+` reserved

## See also

- `data-refinery-cli explain whoami`
- `data-refinery-cli explain doctor`
"""

_WHOAMI = """\
# data-refinery-cli whoami

Reports the agent's identity from `culture.yaml`: nick (`suffix`), backend,
served model, and the package version. Read-only.

## Usage

    data-refinery-cli whoami
    data-refinery-cli whoami --json
"""

_LEARN = """\
# data-refinery-cli learn

Prints a structured self-teaching prompt covering purpose, command map,
exit-code policy, `--json` support, and the `explain` pointer.

## Usage

    data-refinery-cli learn
    data-refinery-cli learn --json
"""

_EXPLAIN = """\
# data-refinery-cli explain <path>

Prints markdown documentation for any noun/verb path. Unlike `--help` (terse,
positional), `explain` is global and addressable by path.

## Usage

    data-refinery-cli explain data-refinery-cli
    data-refinery-cli explain whoami
    data-refinery-cli explain --json <path>
"""

_OVERVIEW = """\
# data-refinery-cli overview

Read-only descriptive snapshot of the agent: identity (from `culture.yaml`), the
verb surface, and the sibling-pattern artifacts the template carries. Accepts an
ignored `target` so a stray path never hard-fails.

## Usage

    data-refinery-cli overview
    data-refinery-cli overview --json
"""

_DOCTOR = """\
# data-refinery-cli doctor

Checks the agent-identity invariants `steward doctor` verifies:
prompt-file-present and backend-consistency (`claude` → `CLAUDE.md`), plus a
skills-present check. Exits 1 when unhealthy.

## Usage

    data-refinery-cli doctor
    data-refinery-cli doctor --json
"""

_CLI = """\
# data-refinery-cli cli

Noun group for CLI-surface introspection. `cli overview` describes the CLI
itself (distinct from the global `overview`, which describes the agent).

## Usage

    data-refinery-cli cli overview
    data-refinery-cli cli overview --json
"""


ENTRIES: dict[tuple[str, ...], str] = {
    (): _ROOT,
    ("data-refinery-cli",): _ROOT,
    ("whoami",): _WHOAMI,
    ("learn",): _LEARN,
    ("explain",): _EXPLAIN,
    ("overview",): _OVERVIEW,
    ("doctor",): _DOCTOR,
    ("cli",): _CLI,
    ("cli", "overview"): _CLI,
}
