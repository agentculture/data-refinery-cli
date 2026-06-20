"""The importable library API (data_refinery.store.put/get/list).

Proves the library surface works AND that it shares one implementation with the
CLI — a put via the library is visible to a CLI list and vice versa (both hit the
same files backend via DR_DATA_DIR).
"""

from __future__ import annotations

import json

import data_refinery.store as store
from data_refinery.cli import main
from data_refinery.store.envelope import Envelope, Scope


def test_put_get_list_round_trip(files_env: str) -> None:
    returned = store.put(Envelope(id="x", content="hi"))
    assert returned.hash == store.content_hash("hi")
    got = store.get("x")
    assert got is not None and got.content == "hi"
    assert [e.id for e in store.list()] == ["x"]


def test_get_missing_returns_none(files_env: str) -> None:
    assert store.get("nope") is None


def test_library_respects_scope_no_leak(files_env: str) -> None:
    store.put(Envelope(id="p", content="secret", scope=Scope("vault", "private")))
    # public-scope library fetch never returns the private doc
    assert store.get("p") is None
    assert store.list() == []
    # matching private scope does
    assert store.get("p", scope=Scope("vault", "private")) is not None


def test_library_and_cli_share_one_store(files_env: str, capsys) -> None:
    # write via the library...
    store.put(Envelope(id="shared", content="hello"))
    # ...read via the CLI
    rc = main(["store", "list", "--json"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert [e["id"] for e in payload] == ["shared"]
