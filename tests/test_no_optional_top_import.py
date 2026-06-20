"""t10 — the optional drivers must never be imported at module top level.

``pymongo`` / ``neo4j`` live behind the ``[store]`` extra and must be
lazy-imported inside function bodies, so importing the package keeps
``dependencies = []`` honest. This statically parses each adapter and asserts no
module-level ``import pymongo`` / ``import neo4j``.
"""

from __future__ import annotations

import ast
from pathlib import Path

import data_refinery.store.backends.mongo as mongo_mod
import data_refinery.store.backends.neo4j as neo4j_mod


def _top_level_imports(module_file: str) -> set[str]:
    tree = ast.parse(Path(module_file).read_text(encoding="utf-8"))
    names: set[str] = set()
    for node in tree.body:  # module body only — not nested in functions
        if isinstance(node, ast.Import):
            names.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module.split(".")[0])
    return names


def test_mongo_adapter_has_no_top_level_pymongo() -> None:
    assert "pymongo" not in _top_level_imports(mongo_mod.__file__)


def test_neo4j_adapter_has_no_top_level_neo4j() -> None:
    assert "neo4j" not in _top_level_imports(neo4j_mod.__file__)


def test_importing_store_does_not_import_drivers() -> None:
    import sys

    # importing the package (and adapters) must not have pulled the drivers
    import data_refinery.store  # noqa: F401
    import data_refinery.store.backends.mongo  # noqa: F401
    import data_refinery.store.backends.neo4j  # noqa: F401

    assert "pymongo" not in sys.modules
    assert "neo4j" not in sys.modules
