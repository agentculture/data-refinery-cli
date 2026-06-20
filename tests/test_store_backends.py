"""Backend-protocol conformance across files / mongo / neo4j.

The ``backend`` fixture (see conftest) parametrises every test over all three
adapters — files uses a real tmp dir; mongo/neo4j use injected offline fakes —
so the CRUD contract and idempotency are proven identically on each.
"""

from __future__ import annotations

from data_refinery.store.envelope import Envelope, Scope


def _env(id: str, content: str, scope: Scope | None = None) -> Envelope:
    return Envelope(id=id, content=content, scope=scope or Scope("default", "public"))


def test_upsert_then_get(backend) -> None:
    backend.upsert(_env("a", "hello"))
    got = backend.get("a", Scope("default", "public"))
    assert got is not None
    assert got.id == "a" and got.content == "hello"


def test_get_missing_returns_none(backend) -> None:
    assert backend.get("nope", Scope("default", "public")) is None


def test_upsert_is_idempotent_by_id(backend) -> None:
    backend.upsert(_env("a", "hello"))
    backend.upsert(_env("a", "hello"))  # same id again
    assert len(backend.all()) == 1


def test_upsert_replaces_content_by_id(backend) -> None:
    backend.upsert(_env("a", "v1"))
    backend.upsert(_env("a", "v2"))
    got = backend.get("a", Scope("default", "public"))
    assert got is not None and got.content == "v2"
    assert len(backend.all()) == 1


def test_list_and_all(backend) -> None:
    backend.upsert(_env("a", "x"))
    backend.upsert(_env("b", "y"))
    ids = {e.id for e in backend.list(Scope("default", "public"))}
    assert ids == {"a", "b"}
    assert {e.id for e in backend.all()} == {"a", "b"}


def test_delete(backend) -> None:
    backend.upsert(_env("a", "x"))
    assert backend.delete("a") is True
    assert backend.get("a", Scope("default", "public")) is None
    assert backend.delete("a") is False  # already gone


def test_metadata_round_trips(backend) -> None:
    backend.upsert(Envelope(id="a", content="x", metadata={"created": "2026-01-01", "n": 3}))
    got = backend.get("a", Scope("default", "public"))
    assert got is not None and got.metadata == {"created": "2026-01-01", "n": 3}
