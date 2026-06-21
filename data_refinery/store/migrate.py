"""Store migration — upgrade an on-disk store to the current Envelope format.

data-refinery owns the storage layout, so it owns the **rewrite**: a consumer
upgrading a populated store supplies only a *transform* (each decoded legacy line
-> an :class:`Envelope`, or ``None`` to drop it) and never constructs a
filesystem write path itself. data-refinery resolves the store root, walks it,
validates every produced envelope, and rewrites **atomically per file**. This is
the endpoint that lets a consumer (eidetic-cli first) delete its own
path-constructing rewrite — moving the write sink to the component that *owns*,
and can reason about, the store directory.

Files granularity ships first; ``mongo`` (vectors) and ``neo4j`` (graph) are a
later granularity and raise a structured error today.
"""

from __future__ import annotations

from typing import Any

from data_refinery.cli._errors import EXIT_USER_ERROR, CliError
from data_refinery.store.backends.files import FilesBackend, Transform

DEFAULT_BACKEND = "files"


def migrate(
    transform: Transform | None = None,
    *,
    backend: str = DEFAULT_BACKEND,
    base_dir: str | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Upgrade an on-disk store to the current Envelope format.

    With ``transform=None`` this re-canonicalises data-refinery's **own**
    Envelope-JSONL (the self-heal / format-version path the ``store migrate`` CLI
    verb uses). With a *transform* the consumer converts each decoded legacy line
    into an :class:`Envelope`; the consumer supplies only the transform (and
    optionally the store root it already owns via *base_dir*) — never a per-file
    write path.

    For re-run idempotency the transform should be a fixpoint on an already-
    Envelope dict; the files backend enforces this for free by keeping an
    already-canonical line verbatim, so a typical transform need not special-case
    it.

    Returns a summary ``{backend, files, migrated, migrated_files, skipped,
    dry_run}``. Idempotent (a second run rewrites nothing) and atomic per file.
    Only the ``files`` backend is supported today; ``mongo``/``neo4j`` raise a
    structured :class:`CliError`.
    """
    if backend == "files":
        return FilesBackend(base_dir).migrate(transform, dry_run=dry_run)
    raise CliError(
        code=EXIT_USER_ERROR,
        message=f"store migration is not yet supported for backend {backend!r}",
        remediation="migrate the 'files' backend today; mongo/neo4j are a later granularity",
    )
