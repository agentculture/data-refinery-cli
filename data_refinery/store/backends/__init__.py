"""Store backend adapters.

``files`` is dependency-free and the default. ``mongo`` and ``neo4j`` are
driver-backed and live behind the optional ``[store]`` extra — each lazy-imports
its driver inside function bodies so importing this package never pulls
``pymongo`` / ``neo4j``.
"""
