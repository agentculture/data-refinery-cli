"""t12 — public/private scope no-leak, enforced across every backend.

The load-bearing privacy invariant: a private-scope document is never returned
by a public-scope fetch. ``can_serve`` is the single chokepoint and every
backend's ``get``/``list`` routes through it; this proves it holds identically on
files / mongo / neo4j (mongo/neo4j via offline fakes).
"""

from __future__ import annotations

from data_refinery.store.envelope import Envelope, Scope

_PUBLIC = Scope("default", "public")
_VAULT = Scope("vault", "private")


def _seed(backend) -> None:
    backend.upsert(Envelope(id="pub", content="shared", scope=_PUBLIC))
    backend.upsert(Envelope(id="priv", content="secret", scope=_VAULT))


def test_public_list_excludes_private(backend) -> None:
    _seed(backend)
    ids = {e.id for e in backend.list(_PUBLIC)}
    assert "pub" in ids
    assert "priv" not in ids  # the private doc must NOT leak to a public list


def test_public_get_cannot_fetch_private(backend) -> None:
    _seed(backend)
    assert backend.get("priv", _PUBLIC) is None  # even a direct id fetch is blocked


def test_matching_private_scope_sees_its_own_and_public(backend) -> None:
    _seed(backend)
    ids = {e.id for e in backend.list(_VAULT)}
    assert ids == {"pub", "priv"}  # private scope sees its own + public docs
    assert backend.get("priv", _VAULT) is not None


def test_different_private_scope_does_not_leak(backend) -> None:
    _seed(backend)
    other = Scope("other", "private")
    assert backend.get("priv", other) is None
    assert "priv" not in {e.id for e in backend.list(other)}


def test_all_is_unfiltered_maintenance_path(backend) -> None:
    _seed(backend)
    # all() deliberately ignores scope so dedup/integrity/freshness see everything
    assert {e.id for e in backend.all()} == {"pub", "priv"}
