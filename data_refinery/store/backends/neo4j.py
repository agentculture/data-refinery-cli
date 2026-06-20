"""Neo4j store backend — behind the optional ``[store]`` extra.

``neo4j`` is **lazy-imported inside ``_get_driver``** (never at module top
level), so importing this module never pulls the driver and the default
``dependencies = []`` invariant holds. A static test asserts the rule. When the
driver is absent the verb exits code ``2`` with an install ``hint:`` — never a
traceback.

Storage-neutral: one ``:Document`` node per envelope (not ``:Memory``), with
``metadata`` stored as a JSON string property and the scope split into
``scope_name`` / ``scope_visibility``. The default URI + no-auth match the
data-refinery stack (``bolt://localhost:7687``).
"""

from __future__ import annotations

import json
import os
from typing import Any

from data_refinery.cli._errors import EXIT_ENV_ERROR, CliError
from data_refinery.store.backend import Backend
from data_refinery.store.envelope import Envelope, Scope, can_serve

_DEFAULT_URI = "bolt://localhost:7687"

_UPSERT = (
    "MERGE (d:Document {id: $id}) "
    "SET d.content = $content, d.hash = $hash, d.metadata = $metadata, "
    "d.scope_name = $scope_name, d.scope_visibility = $scope_visibility "
    "RETURN d.id"
)
_MATCH_ONE = "MATCH (d:Document {id: $id}) RETURN d"
_MATCH_ALL = "MATCH (d:Document) RETURN d"
_DELETE = "MATCH (d:Document {id: $id}) DETACH DELETE d RETURN count(d) AS deleted"


class Neo4jBackend:
    """Persist envelopes as ``:Document`` nodes, one node per envelope."""

    def __init__(
        self,
        driver: Any = None,
        uri: str | None = None,
        user: str | None = None,
        password: str | None = None,
        timeout_ms: int | None = None,
    ) -> None:
        self._driver = driver
        self._uri = uri
        self._user = user
        self._password = password
        self._timeout_ms = timeout_ms

    def close(self) -> None:
        """Close the driver connection (no-op if never connected)."""
        if self._driver is not None:
            self._driver.close()

    # -- Backend protocol ------------------------------------------------

    def upsert(self, envelope: Envelope) -> None:
        self._run(
            _UPSERT,
            {
                "id": envelope.id,
                "content": envelope.content,
                "hash": envelope.hash,
                "metadata": json.dumps(envelope.metadata),
                "scope_name": envelope.scope.name,
                "scope_visibility": envelope.scope.visibility,
            },
        )

    def get(self, id: str, scope: Scope) -> Envelope | None:
        rows = self._run(_MATCH_ONE, {"id": id})
        for row in rows:
            env = self._node_to_envelope(row["d"])
            return env if can_serve(scope, env.scope) else None
        return None

    def list(self, scope: Scope) -> list[Envelope]:
        out: list[Envelope] = []
        for row in self._run(_MATCH_ALL, {}):
            env = self._node_to_envelope(row["d"])
            if can_serve(scope, env.scope):
                out.append(env)
        return out

    def all(self) -> list[Envelope]:
        return [self._node_to_envelope(row["d"]) for row in self._run(_MATCH_ALL, {})]

    def delete(self, id: str) -> bool:
        rows = self._run(_DELETE, {"id": id})
        for row in rows:
            return int(row["deleted"]) > 0
        return False

    # -- internal helpers ------------------------------------------------

    def _get_driver(self) -> Any:
        if self._driver is not None:
            return self._driver
        # The driver import gates the optional [store] extra; the ImportError
        # path is exercised offline (no extra installed). The live connect below
        # needs a real neo4j driver + server, hence its pragma.
        try:
            import neo4j
        except ImportError as exc:
            raise CliError(
                code=EXIT_ENV_ERROR,
                message="the 'neo4j' backend needs the neo4j driver, which is not installed",
                remediation="install the store extra: pip install 'data-refinery-cli[store]'",
            ) from exc
        uri = self._uri or os.environ.get("DR_NEO4J_URI", _DEFAULT_URI)  # pragma: no cover
        user = self._user or os.environ.get("DR_NEO4J_USER")  # pragma: no cover
        password = self._password or os.environ.get("DR_NEO4J_PASSWORD")  # pragma: no cover
        opts: dict[str, Any] = {}  # pragma: no cover
        if self._timeout_ms is not None:  # pragma: no cover
            opts["connection_timeout"] = self._timeout_ms / 1000.0
        try:  # pragma: no cover
            if user and password:
                self._driver = neo4j.GraphDatabase.driver(uri, auth=(user, password), **opts)
            else:
                self._driver = neo4j.GraphDatabase.driver(uri, **opts)
        except Exception as exc:  # pragma: no cover
            raise CliError(
                code=EXIT_ENV_ERROR,
                message=f"failed to connect to Neo4j at {uri}: {exc}",
                remediation="check DR_NEO4J_URI and that the data-refinery stack is up",
            ) from exc
        return self._driver  # pragma: no cover

    def _run(self, query: str, params: dict) -> list[Any]:
        driver = self._get_driver()
        try:
            with driver.session() as session:
                return list(session.run(query, params))
        except CliError:
            raise
        except Exception as exc:
            raise CliError(
                code=EXIT_ENV_ERROR,
                message=f"Neo4j query failed: {exc}",
                remediation="check your Neo4j connection and retry",
            ) from exc

    @staticmethod
    def _node_to_envelope(node: Any) -> Envelope:
        metadata = node.get("metadata", "{}")
        if isinstance(metadata, str):
            metadata = json.loads(metadata or "{}")
        scope = Scope(
            name=node.get("scope_name", "default"),
            visibility=node.get("scope_visibility", "public"),
        )
        return Envelope(
            id=node["id"],
            content=node.get("content", ""),
            scope=scope,
            metadata=metadata,
            hash=node.get("hash", ""),
        )


def build(*, timeout_ms: int | None = None, **_kwargs: object) -> Backend:
    """Factory: a default Neo4jBackend (connects lazily on first use)."""
    return Neo4jBackend(timeout_ms=timeout_ms)
