"""Tests for the ``data-refinery store`` CLI noun.

``store put`` reads a JSON envelope on stdin; under pytest's capture
``sys.stdin.read()`` raises, so each test sets ``sys.stdin`` to a StringIO
explicitly (an empty one selects the --id/--content flag path).
"""

from __future__ import annotations

import io
import json
import sys

import pytest

from data_refinery.cli import main


def _set_stdin(monkeypatch: pytest.MonkeyPatch, text: str) -> None:
    monkeypatch.setattr(sys, "stdin", io.StringIO(text))


# --- overview / explain (no backend needed) ---------------------------


def test_store_no_verb_prints_overview(capsys: pytest.CaptureFixture[str]) -> None:
    rc = main(["store"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "# data-refinery store" in out
    assert "storage-neutral" in out


def test_store_overview_json(capsys: pytest.CaptureFixture[str]) -> None:
    rc = main(["store", "--json"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["subject"] == "data-refinery store"
    assert any(s["title"] == "Backends" for s in payload["sections"])


# --- put / get / list (files backend) ---------------------------------


def test_store_put_from_stdin(
    files_env: str, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _set_stdin(monkeypatch, '{"id":"a","content":"hello"}')
    rc = main(["store", "put", "--json"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["id"] == "a"
    assert payload["hash"]  # filled from content


def test_store_put_from_flags(
    files_env: str, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _set_stdin(monkeypatch, "")  # empty → flag path
    rc = main(["store", "put", "--id", "b", "--content", "yo", "--json"])
    assert rc == 0
    assert json.loads(capsys.readouterr().out)["id"] == "b"


def test_store_get_found_and_missing(
    files_env: str, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _set_stdin(monkeypatch, '{"id":"a","content":"hello"}')
    main(["store", "put"])
    capsys.readouterr()
    rc = main(["store", "get", "a", "--json"])
    assert rc == 0
    found = json.loads(capsys.readouterr().out)
    assert found["found"] is True and found["content"] == "hello"
    rc = main(["store", "get", "ghost", "--json"])
    assert rc == 0
    assert json.loads(capsys.readouterr().out) == {"id": "ghost", "found": False}


def test_store_put_diagnostics_not_in_json(
    files_env: str, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _set_stdin(monkeypatch, '{"id":"a","content":"hello"}')
    main(["store", "put", "--json"])
    captured = capsys.readouterr()
    json.loads(captured.out)  # stdout is pure JSON


# --- error paths (no traceback) ---------------------------------------


def test_store_put_bad_json_exits_1(
    files_env: str, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _set_stdin(monkeypatch, "{not json")
    rc = main(["store", "put"])
    assert rc == 1
    err = capsys.readouterr().err
    assert err.startswith("error:") and "hint:" in err
    assert "Traceback" not in err


def test_store_put_no_input_exits_1(
    files_env: str, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _set_stdin(monkeypatch, "")  # no stdin, no --id
    rc = main(["store", "put"])
    assert rc == 1
    assert "hint:" in capsys.readouterr().err


def test_store_missing_extra_exits_2(
    files_env: str, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    rc = main(["store", "list", "--backend", "mongo"])
    assert rc == 2
    err = capsys.readouterr().err
    assert err.startswith("error:") and "hint:" in err
    assert "[store]" in err
    assert "Traceback" not in err


def test_store_put_stdin_not_object_exits_1(
    files_env: str, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _set_stdin(monkeypatch, "[1, 2, 3]")  # JSON, but not an envelope object
    rc = main(["store", "put"])
    assert rc == 1
    assert "hint:" in capsys.readouterr().err


def test_store_put_stdin_missing_id_exits_1(
    files_env: str, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _set_stdin(monkeypatch, '{"content":"no id"}')
    rc = main(["store", "put"])
    assert rc == 1
    assert "missing 'id'" in capsys.readouterr().err


def test_store_put_stdin_bad_visibility_exits_1(
    files_env: str, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    # The stdin-JSON path must reject an out-of-contract visibility so a typo
    # can never be persisted and later leak to a public fetch.
    _set_stdin(monkeypatch, '{"id":"a","content":"x","scope":{"visibility":"secret"}}')
    rc = main(["store", "put"])
    assert rc == 1
    err = capsys.readouterr().err
    assert err.startswith("error:") and "hint:" in err
    assert "visibility" in err
    assert "Traceback" not in err


# --- human (non-JSON) output paths ------------------------------------


def test_store_put_get_list_text_mode(
    files_env: str, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _set_stdin(monkeypatch, '{"id":"a","content":"hello"}')
    main(["store", "put"])
    assert "stored a (default/public)" in capsys.readouterr().out
    main(["store", "get", "a"])
    assert capsys.readouterr().out.strip() == "hello"  # get prints content
    main(["store", "get", "ghost"])
    assert "not found: ghost" in capsys.readouterr().out
    main(["store", "list"])
    out = capsys.readouterr().out
    assert "- a (default/public)" in out


def test_store_list_empty_text(files_env: str, capsys: pytest.CaptureFixture[str]) -> None:
    main(["store", "list"])
    assert capsys.readouterr().out.strip() == "(empty)"
