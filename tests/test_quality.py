"""Tests for the data-quality checks (library) + verbs (CLI)."""

from __future__ import annotations

import io
import json
import sys

import pytest

from data_refinery.cli import main
from data_refinery.quality import checks
from data_refinery.store.envelope import Envelope, Scope


def _set_stdin(monkeypatch: pytest.MonkeyPatch, text: str) -> None:
    monkeypatch.setattr(sys, "stdin", io.StringIO(text))


# --- validate (pure) ---------------------------------------------------


def test_validate_payload_good_and_bad() -> None:
    assert checks.validate_payload({"id": "a", "content": "x"})["valid"] is True
    bad = checks.validate_payload({"id": "", "content": 1, "scope": {"visibility": "secret"}})
    assert bad["valid"] is False
    assert any("id" in e for e in bad["errors"])
    assert any("content" in e for e in bad["errors"])
    assert any("visibility" in e for e in bad["errors"])


def test_validate_many_aggregates() -> None:
    result = checks.validate_many([{"id": "a", "content": "x"}, {"id": ""}])
    assert result["count"] == 2
    assert result["valid"] is False


# --- dedup (idempotent, via the mongo fake which keeps same-hash dups) --


def test_dedup_collapses_same_hash_then_is_idempotent(mongo_backend) -> None:
    # two distinct ids, identical content (same hash), same scope = duplicates
    mongo_backend.upsert(Envelope(id="a", content="dup"))
    mongo_backend.upsert(Envelope(id="b", content="dup"))
    mongo_backend.upsert(Envelope(id="c", content="unique"))

    first = checks.dedup(mongo_backend)
    assert first["duplicates_removed"] == 1
    remaining = {e.id for e in mongo_backend.all()}
    assert remaining == {"a", "c"}  # first id of the group kept

    second = checks.dedup(mongo_backend)
    assert second["duplicates_removed"] == 0  # idempotent: nothing left to remove
    assert {e.id for e in mongo_backend.all()} == {"a", "c"}


def test_dedup_does_not_cross_scopes(mongo_backend) -> None:
    # same content in different scopes are NOT duplicates (scope isolation)
    mongo_backend.upsert(Envelope(id="pub", content="same", scope=Scope("default", "public")))
    mongo_backend.upsert(Envelope(id="priv", content="same", scope=Scope("vault", "private")))
    result = checks.dedup(mongo_backend)
    assert result["duplicates_removed"] == 0
    assert {e.id for e in mongo_backend.all()} == {"pub", "priv"}


# --- integrity ---------------------------------------------------------


def test_integrity_flags_hash_mismatch() -> None:
    good = Envelope(id="a", content="hello")
    tampered = Envelope(id="b", content="hello", hash="deadbeef")
    result = checks.integrity([good, tampered])
    assert result["ok"] is False
    assert result["checked"] == 2
    assert [m["id"] for m in result["mismatches"]] == ["b"]


# --- freshness (facts, deterministic via now) --------------------------


def test_freshness_reports_age_and_staleness() -> None:
    from datetime import datetime, timezone

    envs = [
        Envelope(id="old", content="x", metadata={"created": "2026-06-01T00:00:00+00:00"}),
        Envelope(id="new", content="y", metadata={"created": "2026-06-20T00:00:00+00:00"}),
        Envelope(id="nodate", content="z"),
    ]
    now = datetime(2026, 6, 20, 0, 0, 0, tzinfo=timezone.utc)
    result = checks.freshness(envs, field="created", max_age=100, now=now)
    by_id = {r["id"]: r for r in result["results"]}
    assert by_id["old"]["stale"] is True
    assert by_id["new"]["stale"] is False and by_id["new"]["age_seconds"] == 0
    assert by_id["nodate"]["age_seconds"] is None  # missing timestamp → fact, not error
    assert result["stale"] == 1


# --- CLI verbs ---------------------------------------------------------


def test_validate_cli_reports_invalid(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _set_stdin(monkeypatch, '[{"id":"a","content":"x"},{"id":""}]')
    rc = main(["validate", "--json"])
    assert rc == 0  # the check ran; findings ride in the payload
    payload = json.loads(capsys.readouterr().out)
    assert payload["valid"] is False and payload["count"] == 2


def test_validate_cli_no_stdin_exits_1(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _set_stdin(monkeypatch, "")
    rc = main(["validate"])
    assert rc == 1
    assert "hint:" in capsys.readouterr().err


def test_integrity_cli_on_files_store(files_env: str, capsys: pytest.CaptureFixture[str]) -> None:
    import data_refinery.store as store

    store.put(Envelope(id="a", content="hello"))
    rc = main(["integrity", "--json"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True and payload["checked"] == 1


def test_dedup_cli_idempotent_on_files(files_env: str, capsys: pytest.CaptureFixture[str]) -> None:
    import data_refinery.store as store

    store.put(Envelope(id="a", content="hello"))
    rc = main(["dedup", "--json"])
    assert rc == 0
    assert json.loads(capsys.readouterr().out)["duplicates_removed"] == 0


def test_freshness_cli_deterministic(files_env: str, capsys: pytest.CaptureFixture[str]) -> None:
    import data_refinery.store as store

    store.put(Envelope(id="a", content="x", metadata={"created": "2026-06-01T00:00:00+00:00"}))
    rc = main(
        [
            "freshness",
            "--field",
            "created",
            "--max-age",
            "100",
            "--now",
            "2026-06-20T00:00:00+00:00",
            "--json",
        ]
    )
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["stale"] == 1 and payload["checked"] == 1


def test_freshness_cli_bad_now_exits_1(files_env: str, capsys: pytest.CaptureFixture[str]) -> None:
    rc = main(["freshness", "--now", "not-a-date"])
    assert rc == 1
    assert "hint:" in capsys.readouterr().err


# --- human (non-JSON) output paths ------------------------------------


def test_validate_cli_text_mode(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _set_stdin(monkeypatch, '[{"id":"a","content":"x"},{"id":""}]')
    main(["validate"])
    out = capsys.readouterr().out
    assert "valid: 1/2" in out
    assert "- " in out  # the invalid row's errors are listed


def test_dedup_integrity_freshness_text_mode(
    files_env: str, capsys: pytest.CaptureFixture[str]
) -> None:
    import data_refinery.store as store

    store.put(Envelope(id="a", content="x", metadata={"created": "2026-06-01T00:00:00+00:00"}))
    main(["dedup"])
    assert "dedup: removed 0 duplicate(s)" in capsys.readouterr().out
    main(["integrity"])
    assert "ok: True (1 checked)" in capsys.readouterr().out
    main(["freshness", "--now", "2026-06-20T00:00:00+00:00", "--max-age", "100"])
    assert "freshness: 1 checked, 1 stale" in capsys.readouterr().out


def test_integrity_cli_text_mode_reports_mismatch(
    files_env: str, capsys: pytest.CaptureFixture[str]
) -> None:
    # write a tampered envelope (hash != sha256(content)) straight to the store
    from data_refinery.store.backends.files import FilesBackend

    FilesBackend(base_dir=files_env).upsert(Envelope(id="t", content="hello", hash="deadbeef"))
    main(["integrity"])
    out = capsys.readouterr().out
    assert "ok: False" in out
    assert "- t:" in out
