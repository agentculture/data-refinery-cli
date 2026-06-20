"""Tests for the storage-neutral Envelope + scope policy."""

from __future__ import annotations

from data_refinery.store.envelope import (
    DEFAULT_SCOPE,
    Envelope,
    Scope,
    can_serve,
    content_hash,
)


def test_hash_filled_from_content_when_absent() -> None:
    env = Envelope(id="a", content="hello")
    assert env.hash == content_hash("hello")
    # explicit hash is preserved
    assert Envelope(id="a", content="hello", hash="deadbeef").hash == "deadbeef"


def test_default_scope_is_public_default() -> None:
    env = Envelope(id="a", content="x")
    assert env.scope == DEFAULT_SCOPE == Scope("default", "public")


def test_to_dict_round_trips() -> None:
    env = Envelope(
        id="a",
        content="hello",
        scope=Scope("vault", "private"),
        metadata={"created": "2026-01-01", "lifecycle": "active"},
    )
    again = Envelope.from_dict(env.to_dict())
    assert again == env
    # storage-neutral: only the five fields, no memory keys
    assert set(env.to_dict()) == {"id", "hash", "content", "scope", "metadata"}


def test_from_dict_tolerates_missing_optional_fields() -> None:
    env = Envelope.from_dict({"id": "a"})
    assert env.content == ""
    assert env.scope == DEFAULT_SCOPE
    assert env.metadata == {}
    assert env.hash == content_hash("")


def test_metadata_coerced_to_dict() -> None:
    assert Envelope.from_dict({"id": "a", "metadata": None}).metadata == {}


def test_can_serve_policy() -> None:
    pub = Scope("default", "public")
    priv = Scope("vault", "private")
    # public served to anyone
    assert can_serve(pub, pub) is True
    assert can_serve(priv, pub) is True
    # private served only to the exact same scope
    assert can_serve(priv, priv) is True
    assert can_serve(pub, priv) is False
    assert can_serve(Scope("other", "private"), priv) is False
