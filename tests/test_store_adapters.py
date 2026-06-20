"""Adapter-specific tests for the mongo / neo4j backends (offline).

CRUD + scope are covered generically in test_store_backends / test_scope_no_leak
via the parametrised ``backend`` fixture. Here we cover the bits unique to each
driver-backed adapter: the missing-driver error path, and the document/node
shape round-trip through the injected fakes.
"""

from __future__ import annotations

import pytest

from data_refinery.cli._errors import CliError
from data_refinery.store.backends.mongo import MongoBackend
from data_refinery.store.backends.neo4j import Neo4jBackend
from data_refinery.store.envelope import Envelope, Scope

# --- missing optional driver → CliError code 2 (no traceback) -----------


def test_mongo_missing_driver_raises_cli_error() -> None:
    backend = MongoBackend()  # no injected client → real lazy import
    with pytest.raises(CliError) as exc:
        backend.list(Scope("default", "public"))
    assert exc.value.code == 2
    assert "pymongo" in exc.value.message
    assert "[store]" in exc.value.remediation


def test_neo4j_missing_driver_raises_cli_error() -> None:
    backend = Neo4jBackend()  # no injected driver → real lazy import
    with pytest.raises(CliError) as exc:
        backend.list(Scope("default", "public"))
    assert exc.value.code == 2
    assert "neo4j" in exc.value.message
    assert "[store]" in exc.value.remediation


# --- mongo doc shape ----------------------------------------------------


def test_mongo_stores_id_as_mongo_key(mongo_backend) -> None:
    mongo_backend.upsert(Envelope(id="a", content="hi"))
    collection = mongo_backend._collection
    assert "a" in collection.docs
    assert collection.docs["a"]["_id"] == "a"
    assert collection.docs["a"]["content"] == "hi"


def test_mongo_delete_missing_is_false(mongo_backend) -> None:
    assert mongo_backend.delete("ghost") is False


# --- neo4j node shape ---------------------------------------------------


def test_neo4j_serialises_metadata_as_json(neo4j_backend) -> None:
    neo4j_backend.upsert(Envelope(id="a", content="hi", metadata={"k": "v"}))
    node = neo4j_backend._driver._store["a"]
    assert node["metadata"] == '{"k": "v"}'  # stored as a JSON string property
    got = neo4j_backend.get("a", Scope("default", "public"))
    assert got is not None and got.metadata == {"k": "v"}


def test_neo4j_delete_missing_is_false(neo4j_backend) -> None:
    assert neo4j_backend.delete("ghost") is False


def test_neo4j_query_error_wrapped_as_cli_error() -> None:
    class _Boom:
        def session(self):  # noqa: ANN201
            raise RuntimeError("bolt down")

    backend = Neo4jBackend(driver=_Boom())
    with pytest.raises(CliError) as exc:
        backend.all()
    assert exc.value.code == 2
    assert "Neo4j query failed" in exc.value.message


def test_adapters_close_is_safe(mongo_backend, neo4j_backend) -> None:
    # close() is a no-op pass-through to the injected client/driver
    mongo_backend.close()
    neo4j_backend.close()
    MongoBackend().close()  # never connected → no-op
    Neo4jBackend().close()
