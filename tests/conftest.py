"""Shared fixtures + offline fakes for the store/quality tests.

The mongo/neo4j adapters take an injected ``client``/``driver`` so their
Python-side logic (envelope round-trip, ``can_serve`` filtering, delete) is fully
covered **without** ``pymongo``/``neo4j`` installed and without a live database —
the lazy driver import is never reached when a client/driver is injected.

The neo4j fake classifies queries against the adapter's own query *constants*
(imported here), so it stays in lock-step with the production Cypher.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from data_refinery.store.backends import neo4j as _neo4j_mod
from data_refinery.store.backends.files import FilesBackend
from data_refinery.store.backends.mongo import MongoBackend
from data_refinery.store.backends.neo4j import Neo4jBackend

# --- fake mongo (dict-backed) -----------------------------------------


def _doc_matches(doc: dict, filt: dict) -> bool:
    """Match *doc* against a mongo-style filter, honouring dotted paths.

    Supports the filters the adapter actually issues — flat keys (``hash``) and
    dotted keys into the embedded scope (``scope.name``/``scope.visibility``).
    """
    for key, want in filt.items():
        cur: object = doc
        for part in key.split("."):
            if not isinstance(cur, dict) or part not in cur:
                cur = None
                break
            cur = cur[part]
        if cur != want:
            return False
    return True


class FakeMongoCollection:
    def __init__(self) -> None:
        self.docs: dict[str, dict] = {}

    def replace_one(self, filt, doc, upsert=False):  # noqa: ANN001
        self.docs[filt["_id"]] = dict(doc)
        return SimpleNamespace(matched_count=1, upserted_id=filt["_id"])

    def find_one(self, filt):  # noqa: ANN001
        return self.docs.get(filt["_id"])

    def find(self, _filt):  # noqa: ANN001
        return list(self.docs.values())

    def delete_one(self, filt):  # noqa: ANN001
        existed = filt["_id"] in self.docs
        self.docs.pop(filt["_id"], None)
        return SimpleNamespace(deleted_count=1 if existed else 0)

    def delete_many(self, filt):  # noqa: ANN001
        to_del = [k for k, d in self.docs.items() if _doc_matches(d, filt)]
        for k in to_del:
            del self.docs[k]
        return SimpleNamespace(deleted_count=len(to_del))


class _FakeMongoDB:
    def __init__(self) -> None:
        self._cols: dict[str, FakeMongoCollection] = {}

    def __getitem__(self, name: str) -> FakeMongoCollection:
        return self._cols.setdefault(name, FakeMongoCollection())


class FakeMongoClient:
    def __init__(self) -> None:
        self._dbs: dict[str, _FakeMongoDB] = {}

    def __getitem__(self, name: str) -> _FakeMongoDB:
        return self._dbs.setdefault(name, _FakeMongoDB())

    def close(self) -> None:  # pragma: no cover - parity with the real client
        pass


# --- fake neo4j (query-constant aware) --------------------------------


class _FakeNeo4jSession:
    def __init__(self, store: dict[str, dict]) -> None:
        self._store = store

    def __enter__(self) -> "_FakeNeo4jSession":
        return self

    def __exit__(self, *_exc) -> bool:  # noqa: ANN002
        return False

    def run(self, query: str, params: dict):  # noqa: ANN001
        if query == _neo4j_mod._UPSERT:
            self._store[params["id"]] = {
                "id": params["id"],
                "content": params["content"],
                "hash": params["hash"],
                "metadata": params["metadata"],
                "scope_name": params["scope_name"],
                "scope_visibility": params["scope_visibility"],
            }
            return [{"d.id": params["id"]}]
        if query == _neo4j_mod._MATCH_ONE:
            node = self._store.get(params["id"])
            return [{"d": node}] if node is not None else []
        if query == _neo4j_mod._MATCH_ALL:
            return [{"d": node} for node in self._store.values()]
        if query == _neo4j_mod._DELETE:
            existed = self._store.pop(params["id"], None) is not None
            return [{"deleted": 1 if existed else 0}]
        if query == _neo4j_mod._DEDUP_BY_HASH:
            to_del = [
                k
                for k, n in self._store.items()
                if n["hash"] == params["hash"]
                and n["scope_name"] == params["scope_name"]
                and n["scope_visibility"] == params["scope_visibility"]
            ]
            for k in to_del:
                del self._store[k]
            return []
        return []


class FakeNeo4jDriver:
    def __init__(self) -> None:
        self._store: dict[str, dict] = {}

    def session(self) -> _FakeNeo4jSession:
        return _FakeNeo4jSession(self._store)

    def close(self) -> None:  # pragma: no cover - parity with the real driver
        pass


# --- fixtures ----------------------------------------------------------


@pytest.fixture
def files_backend(tmp_path) -> FilesBackend:
    return FilesBackend(base_dir=str(tmp_path / "store"))


@pytest.fixture
def mongo_backend() -> MongoBackend:
    return MongoBackend(client=FakeMongoClient())


@pytest.fixture
def neo4j_backend() -> Neo4jBackend:
    return Neo4jBackend(driver=FakeNeo4jDriver())


@pytest.fixture(params=["files", "mongo", "neo4j"])
def backend(request, tmp_path):
    """Every backend, exercised through the same offline path."""
    if request.param == "files":
        return FilesBackend(base_dir=str(tmp_path / "store"))
    if request.param == "mongo":
        return MongoBackend(client=FakeMongoClient())
    return Neo4jBackend(driver=FakeNeo4jDriver())


@pytest.fixture
def files_env(tmp_path, monkeypatch) -> str:
    """Point the CLI's default files backend at a throwaway dir (never $HOME)."""
    data_dir = str(tmp_path / "store")
    monkeypatch.setenv("DR_DATA_DIR", data_dir)
    return data_dir
