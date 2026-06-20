"""MongoDB store backend — behind the optional ``[store]`` extra.

``pymongo`` is **lazy-imported inside function bodies** (never at module top
level), so importing this module is cheap and the default ``dependencies = []``
invariant holds. A static test (``tests/test_no_optional_top_import.py``) asserts
the no-top-level-import rule. When the driver is absent the verb exits code ``2``
with an install ``hint:`` — never a traceback.

Storage-neutral: stores opaque :class:`Envelope` documents with **no
embeddings** and no memory fields. The default URI matches the data-refinery
stack (``mongodb://localhost:27018``).
"""

from __future__ import annotations

import os
from typing import Any

from data_refinery.cli._errors import EXIT_ENV_ERROR, CliError
from data_refinery.store.backend import Backend
from data_refinery.store.envelope import Envelope, Scope, can_serve

_DEFAULT_URI = "mongodb://localhost:27018"
_DEFAULT_DB = "data_refinery"
_COLLECTION = "envelopes"


class MongoBackend:
    """Persist envelopes in a MongoDB collection (one document per envelope)."""

    def __init__(
        self,
        client: Any = None,
        uri: str | None = None,
        db: str | None = None,
        timeout_ms: int | None = None,
    ) -> None:
        self._client = client
        self._uri = uri or os.environ.get("DR_MONGO_URI") or _DEFAULT_URI
        self._db_name = db or os.environ.get("DR_MONGO_DB") or _DEFAULT_DB
        self._timeout_ms = timeout_ms if timeout_ms is not None else 5000

    # -- lazy client ----------------------------------------------------

    def _ensure_client(self) -> Any:
        if self._client is not None:
            return self._client
        # The driver import is the gate for the optional [store] extra; the
        # ImportError path is exercised offline (no extra installed). Only the
        # live connect below needs a real pymongo + server, hence its pragma.
        try:
            from pymongo import MongoClient
        except ImportError as exc:
            raise CliError(
                code=EXIT_ENV_ERROR,
                message="the 'mongo' backend needs pymongo, which is not installed",
                remediation="install the store extra: pip install 'data-refinery-cli[store]'",
            ) from exc
        try:  # pragma: no cover - needs a live pymongo + server
            self._client = MongoClient(self._uri, serverSelectionTimeoutMS=self._timeout_ms)
        except Exception as exc:  # pragma: no cover
            raise CliError(
                code=EXIT_ENV_ERROR,
                message=f"failed to connect to MongoDB at {self._uri}: {exc}",
                remediation="check DR_MONGO_URI and that the data-refinery stack is up",
            ) from exc
        return self._client  # pragma: no cover

    @property
    def _collection(self) -> Any:
        return self._ensure_client()[self._db_name][_COLLECTION]

    def close(self) -> None:
        """Close the client connection (no-op if never connected)."""
        if self._client is not None:
            self._client.close()

    # -- Backend protocol ------------------------------------------------

    def upsert(self, envelope: Envelope) -> None:
        """Idempotent by id; dedups by content hash within the scope on insert.

        Mirrors the files backend: when *id* is new, drop any other envelope
        with the same content hash in the same scope so re-putting identical
        content under a new id never accumulates duplicates. Replacing an
        existing id leaves same-hash neighbours untouched (it is not an insert).
        """
        coll = self._collection
        doc = envelope.to_dict()
        doc["_id"] = envelope.id
        if coll.find_one({"_id": envelope.id}) is None:
            coll.delete_many(
                {
                    "hash": envelope.hash,
                    "scope.name": envelope.scope.name,
                    "scope.visibility": envelope.scope.visibility,
                }
            )
        coll.replace_one({"_id": envelope.id}, doc, upsert=True)

    def get(self, id: str, scope: Scope) -> Envelope | None:
        doc = self._collection.find_one({"_id": id})
        if doc is None:
            return None
        env = Envelope.from_dict(doc)
        return env if can_serve(scope, env.scope) else None

    def list(self, scope: Scope) -> list[Envelope]:
        out: list[Envelope] = []
        for doc in self._collection.find({}):
            env = Envelope.from_dict(doc)
            if can_serve(scope, env.scope):
                out.append(env)
        return out

    def all(self) -> list[Envelope]:
        return [Envelope.from_dict(doc) for doc in self._collection.find({})]

    def delete(self, id: str) -> bool:
        result = self._collection.delete_one({"_id": id})
        return getattr(result, "deleted_count", 0) > 0


def build(*, timeout_ms: int | None = None, **_kwargs: object) -> Backend:
    """Factory: a default MongoBackend (connects lazily on first use)."""
    return MongoBackend(timeout_ms=timeout_ms)
