"""Store migration endpoint — files granularity (issue #8).

data-refinery owns the on-disk layout, so it owns the rewrite. These tests prove
the load-bearing guarantees: a consumer supplies only a *transform* (never a
write path), the rewrite is **idempotent** (a 2nd run is byte-identical) and
**atomic per file** (an abort leaves the original intact), every produced
envelope is validated before any write, and the files-first seam holds
(`mongo`/`neo4j` raise today).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import data_refinery.store as store
import data_refinery.store.backends.files as files_mod
from data_refinery.cli import main
from data_refinery.cli._errors import CliError
from data_refinery.store.backends.files import FilesBackend
from data_refinery.store.envelope import Envelope, Scope

# A line already in data-refinery's own canonical-ish shape (but missing `hash`).
_NEEDS_HASH = {
    "id": "a",
    "content": "hello",
    "scope": {"name": "default", "visibility": "public"},
    "metadata": {},
}


def _write_lines(path: Path, objs: list[dict]) -> None:
    path.write_text("".join(json.dumps(o) + "\n" for o in objs), encoding="utf-8")


def _read_lines(path: Path) -> list[dict]:
    return [json.loads(ln) for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()]


def _seed(tmp_path: Path, objs: list[dict], name: str = "default__public.jsonl") -> Path:
    base = tmp_path / "store"
    base.mkdir(exist_ok=True)
    path = base / name
    _write_lines(path, objs)
    return base


# --- self-canonicalise (transform=None) -------------------------------------


def test_self_canonicalize_fills_missing_hash(tmp_path: Path) -> None:
    base = _seed(tmp_path, [_NEEDS_HASH])
    result = FilesBackend(base_dir=str(base)).migrate()  # transform=None
    assert result == {
        "backend": "files",
        "files": 1,
        "migrated": 1,
        "migrated_files": ["default__public.jsonl"],
        "skipped": 0,
        "dry_run": False,
    }
    assert _read_lines(base / "default__public.jsonl")[0]["hash"] == store.content_hash("hello")


def test_migrate_is_idempotent(tmp_path: Path) -> None:
    base = _seed(tmp_path, [_NEEDS_HASH])
    backend = FilesBackend(base_dir=str(base))
    backend.migrate()
    canonical = (base / "default__public.jsonl").read_bytes()
    second = backend.migrate()
    assert second["migrated"] == 0 and second["skipped"] == 1
    assert (base / "default__public.jsonl").read_bytes() == canonical  # byte-identical


def test_already_canonical_store_is_left_untouched(tmp_path: Path) -> None:
    # A file written by the backend itself is already canonical -> 0 migrated.
    base = tmp_path / "store"
    backend = FilesBackend(base_dir=str(base))
    backend.upsert(Envelope(id="a", content="hello"))
    before = (base / "default__public.jsonl").read_bytes()
    result = backend.migrate()
    assert result["migrated"] == 0 and result["skipped"] == 1
    assert (base / "default__public.jsonl").read_bytes() == before


# --- consumer transform path ------------------------------------------------


def test_transform_converts_legacy_then_is_idempotent(tmp_path: Path) -> None:
    # An arbitrary legacy shape data-refinery knows nothing about.
    base = _seed(tmp_path, [{"key": "a", "value": "hello", "vis": "public"}], name="legacy.jsonl")

    def transform(raw: dict) -> Envelope:
        return Envelope(id=raw["key"], content=raw["value"], scope=Scope("default", raw["vis"]))

    backend = FilesBackend(base_dir=str(base))
    first = backend.migrate(transform)
    assert first["migrated"] == 1
    row = _read_lines(base / "legacy.jsonl")[0]
    assert row["id"] == "a" and row["content"] == "hello"
    assert row["hash"] == store.content_hash("hello")

    # 2nd run: the line is now a canonical Envelope and is kept verbatim — the
    # transform (which would KeyError on raw["key"]) is never re-applied.
    second = backend.migrate(transform)
    assert second["migrated"] == 0 and second["skipped"] == 1


def test_transform_returning_none_drops_the_record(tmp_path: Path) -> None:
    base = _seed(
        tmp_path,
        [{"key": "keep", "value": "x"}, {"key": "drop", "value": "y", "tombstone": True}],
        name="legacy.jsonl",
    )

    def transform(raw: dict) -> Envelope | None:
        if raw.get("tombstone"):
            return None
        return Envelope(id=raw["key"], content=raw["value"])

    FilesBackend(base_dir=str(base)).migrate(transform)
    assert [r["id"] for r in _read_lines(base / "legacy.jsonl")] == ["keep"]


def test_consumer_supplies_only_a_transform_via_library(tmp_path: Path) -> None:
    base = _seed(tmp_path, [_NEEDS_HASH])
    # The public library entry point — consumer passes a root it owns, no path.
    result = store.migrate(base_dir=str(base))
    assert result["migrated"] == 1
    assert _read_lines(base / "default__public.jsonl")[0]["hash"] == store.content_hash("hello")


# --- validation / abort-safety ----------------------------------------------


def test_unknown_visibility_aborts_before_any_write(tmp_path: Path) -> None:
    base = _seed(tmp_path, [{"key": "a", "value": "hello"}], name="legacy.jsonl")
    before = (base / "legacy.jsonl").read_bytes()

    def transform(raw: dict) -> Envelope:
        return Envelope(id=raw["key"], content=raw["value"], scope=Scope("default", "secret"))

    with pytest.raises(CliError) as exc:
        FilesBackend(base_dir=str(base)).migrate(transform)
    assert exc.value.code == 1
    assert (base / "legacy.jsonl").read_bytes() == before  # untouched


def test_corrupt_source_line_aborts_with_code_2(tmp_path: Path) -> None:
    base = tmp_path / "store"
    base.mkdir()
    path = base / "default__public.jsonl"
    path.write_text(
        json.dumps(_NEEDS_HASH) + "\n" + "{not json\n",
        encoding="utf-8",
    )
    before = path.read_bytes()
    with pytest.raises(CliError) as exc:
        FilesBackend(base_dir=str(base)).migrate()
    assert exc.value.code == 2
    assert path.read_bytes() == before  # untouched


def test_atomic_write_failure_leaves_original_intact(tmp_path: Path, monkeypatch) -> None:
    base = _seed(tmp_path, [_NEEDS_HASH])
    path = base / "default__public.jsonl"
    before = path.read_bytes()

    def boom(_src, _dst):
        raise OSError("simulated crash before the atomic swap")

    monkeypatch.setattr(files_mod.os, "replace", boom)
    with pytest.raises(OSError):
        FilesBackend(base_dir=str(base)).migrate()
    assert path.read_bytes() == before  # original intact — os.replace never ran
    assert list(base.glob("*.tmp")) == []  # temp sibling cleaned up


def test_symlinked_scope_file_outside_root_is_refused(tmp_path: Path) -> None:
    base = tmp_path / "store"
    base.mkdir()
    outside = tmp_path / "outside.jsonl"
    _write_lines(outside, [_NEEDS_HASH])
    (base / "default__public.jsonl").symlink_to(outside)
    with pytest.raises(CliError) as exc:
        FilesBackend(base_dir=str(base)).migrate()
    assert exc.value.code == 2
    assert "store root" in exc.value.message


# --- dry-run + files-first seam ---------------------------------------------


def test_dry_run_reports_without_writing(tmp_path: Path) -> None:
    base = _seed(tmp_path, [_NEEDS_HASH])
    before = (base / "default__public.jsonl").read_bytes()
    result = FilesBackend(base_dir=str(base)).migrate(dry_run=True)
    assert result["migrated"] == 1 and result["dry_run"] is True
    assert (base / "default__public.jsonl").read_bytes() == before  # nothing written


@pytest.mark.parametrize("backend", ["mongo", "neo4j"])
def test_unsupported_backend_raises(tmp_path: Path, backend: str) -> None:
    with pytest.raises(CliError) as exc:
        store.migrate(backend=backend, base_dir=str(tmp_path))
    assert exc.value.code == 1
    assert backend in exc.value.message


# --- atomic upsert (the shared helper also fixes the day-to-day write) -------


def test_upsert_is_atomic_and_leaves_no_temp(tmp_path: Path) -> None:
    backend = FilesBackend(base_dir=str(tmp_path / "store"))
    backend.upsert(Envelope(id="a", content="x"))
    backend.upsert(Envelope(id="b", content="y"))
    assert list((tmp_path / "store").glob("*.tmp")) == []
    assert {e.id for e in backend.all()} == {"a", "b"}


# --- CLI verb ----------------------------------------------------------------


def test_cli_store_migrate_json_then_idempotent(files_env: str, capsys) -> None:
    base = Path(files_env)
    base.mkdir(parents=True, exist_ok=True)
    _write_lines(base / "default__public.jsonl", [_NEEDS_HASH])

    assert main(["store", "migrate", "--json"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["backend"] == "files" and out["migrated"] == 1

    assert main(["store", "migrate", "--json"]) == 0  # idempotent
    assert json.loads(capsys.readouterr().out)["migrated"] == 0


def test_cli_store_migrate_dry_run_text(files_env: str, capsys) -> None:
    base = Path(files_env)
    base.mkdir(parents=True, exist_ok=True)
    _write_lines(base / "default__public.jsonl", [_NEEDS_HASH])
    assert main(["store", "migrate", "--dry-run"]) == 0
    assert "would migrate" in capsys.readouterr().out


def test_cli_store_migrate_unsupported_backend_exits_1(files_env: str, capsys) -> None:
    # JSON mode: a structured error line on stderr (never a traceback).
    assert main(["store", "migrate", "--backend", "neo4j", "--json"]) == 1
    err = json.loads(capsys.readouterr().err)
    assert err["code"] == 1 and "neo4j" in err["message"] and err["remediation"]

    # Text mode: the same error renders the load-bearing `hint:` prefix.
    assert main(["store", "migrate", "--backend", "mongo"]) == 1
    assert "hint:" in capsys.readouterr().err
