"""data-refinery's importable store API.

A consumer can either shell out (``data-refinery store put|get|list``) or import
this module — both share **one** implementation (the same :func:`get_backend`
resolver and backend adapters). The surface is storage-neutral: it moves opaque
:class:`Envelope` documents, never memory records.

    import data_refinery.store as store

    store.put(store.Envelope(id="a", content="hello"))
    store.get("a")            # -> Envelope | None
    store.list()              # -> list[Envelope]

The ``backend`` keyword selects ``files`` (default, dependency-free), ``mongo``,
or ``neo4j`` (the last two need the optional ``[store]`` extra).
"""

from __future__ import annotations

from data_refinery.store.backend import DEFAULT_BACKEND, Backend, get_backend
from data_refinery.store.envelope import (
    DEFAULT_SCOPE,
    Envelope,
    Scope,
    Visibility,
    can_serve,
    content_hash,
)
from data_refinery.store.migrate import migrate

__all__ = [
    "Envelope",
    "Scope",
    "Visibility",
    "DEFAULT_SCOPE",
    "can_serve",
    "content_hash",
    "Backend",
    "get_backend",
    "put",
    "get",
    "list",
    "migrate",
]


def put(envelope: Envelope, *, backend: str = DEFAULT_BACKEND, **kwargs: object) -> Envelope:
    """Upsert *envelope* into the store and return it (with its hash filled)."""
    get_backend(backend, **kwargs).upsert(envelope)
    return envelope


def get(
    id: str,
    *,
    scope: Scope = DEFAULT_SCOPE,
    backend: str = DEFAULT_BACKEND,
    **kwargs: object,
) -> Envelope | None:
    """Fetch the envelope with *id* visible to *scope*, or None."""
    return get_backend(backend, **kwargs).get(id, scope)


# `list` shadows the builtin within this module by design — the contract is
# `data_refinery.store.list`. The body never needs the builtin (it returns the
# backend's list verbatim), and the dev flake8 has no flake8-builtins plugin.
def list(  # noqa: A001
    *,
    scope: Scope = DEFAULT_SCOPE,
    backend: str = DEFAULT_BACKEND,
    **kwargs: object,
) -> list[Envelope]:
    """List every envelope visible to *scope*."""
    return get_backend(backend, **kwargs).list(scope)
