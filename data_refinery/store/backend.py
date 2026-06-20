"""Backend Protocol + resolver for the data-refinery store.

A backend persists :class:`~data_refinery.store.envelope.Envelope` documents.
The contract is small and storage-neutral:

* ``upsert`` — insert/replace by id (idempotent); dedup by hash on insert.
* ``get`` / ``list`` — **scope-filtered** reads (apply :func:`can_serve`); a
  private document never leaks to a public-scope query.
* ``all`` — **unfiltered** enumeration (the maintenance path used by
  ``dedup`` / ``integrity`` / ``freshness``); it sees every document regardless
  of scope and never mutates.
* ``delete`` — hard delete by id. data-refinery is storage-neutral and may
  hard-delete; it does **not** inherit eidetic's no-hard-delete lifecycle.

The driver-backed backends (``mongo``, ``neo4j``) live behind the optional
``[store]`` extra and lazy-import their driver inside function bodies, so
importing this package never pulls ``neo4j`` / ``pymongo`` and the default
``dependencies = []`` invariant holds.
"""

from __future__ import annotations

import importlib
from typing import Protocol

from data_refinery.cli._errors import EXIT_ENV_ERROR, CliError
from data_refinery.store.envelope import Envelope, Scope

DEFAULT_BACKEND = "files"
_KNOWN_BACKENDS: set[str] = {"files", "mongo", "neo4j"}


class Backend(Protocol):
    """Minimal interface for an envelope storage backend."""

    def upsert(self, envelope: Envelope) -> None: ...

    def get(self, id: str, scope: Scope) -> Envelope | None: ...

    def list(self, scope: Scope) -> list[Envelope]: ...

    def all(self) -> list[Envelope]: ...

    def delete(self, id: str) -> bool: ...


def get_backend(name: str = DEFAULT_BACKEND, **kwargs: object) -> Backend:
    """Resolve a backend by name, raising :class:`CliError` on failure.

    ``files`` is dependency-free and always available. ``mongo`` / ``neo4j`` need
    the optional ``[store]`` extra; their driver import is lazy (inside the
    adapter), so an absent driver surfaces as a structured code-2 error with an
    install ``hint:`` when the verb actually runs — not at import time.
    """
    if name not in _KNOWN_BACKENDS:
        raise CliError(
            code=EXIT_ENV_ERROR,
            message=f"unknown store backend: {name!r}",
            remediation=f"available backends: {', '.join(sorted(_KNOWN_BACKENDS))}",
        )
    module = importlib.import_module(f"data_refinery.store.backends.{name}")
    return module.build(**kwargs)  # type: ignore[no-any-return]
