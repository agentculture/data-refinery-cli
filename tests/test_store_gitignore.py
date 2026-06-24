"""Files-backend .gitignore materialization (issue #12).

When ``write_gitignore=True`` is passed to ``FilesBackend`` (or forwarded
through ``store.put`` / ``store.migrate``), the backend creates a fail-closed
``.gitignore`` on the first write, ignoring everything except public shards.
Reads never create the file; existing files are never overwritten.
"""

from __future__ import annotations

import shutil
import subprocess

import pytest

import data_refinery.store as store
from data_refinery.store.backends.files import FilesBackend, build
from data_refinery.store.envelope import Envelope, Scope

_GITIGNORE_CONTENT = "*\n!.gitignore\n!*__public.jsonl\n"


# ------------------------------------------------------------------
# Content / existence
# ------------------------------------------------------------------


def test_gitignore_content_after_upsert(tmp_path) -> None:
    """A write_gitignore=True upsert creates .gitignore with the canonical content."""
    backend = FilesBackend(base_dir=str(tmp_path), write_gitignore=True)
    backend.upsert(Envelope(id="a", content="hello"))
    gi = tmp_path / ".gitignore"
    assert gi.exists()
    assert gi.read_text() == _GITIGNORE_CONTENT


def test_default_no_gitignore(tmp_path) -> None:
    """Default (write_gitignore=False) never creates .gitignore."""
    backend = FilesBackend(base_dir=str(tmp_path))
    backend.upsert(Envelope(id="a", content="hello"))
    assert not (tmp_path / ".gitignore").exists()


def test_read_does_not_create_gitignore(tmp_path) -> None:
    """get()/list() with write_gitignore=True must NOT create .gitignore."""
    backend = FilesBackend(base_dir=str(tmp_path), write_gitignore=True)
    # No envelopes yet — reads on an empty store
    assert backend.get("nope", Scope("default", "public")) is None
    assert backend.list(Scope("default", "public")) == []
    assert not (tmp_path / ".gitignore").exists()


def test_existing_gitignore_never_overwritten(tmp_path) -> None:
    """A pre-existing .gitignore with different content is never clobbered."""
    gi = tmp_path / ".gitignore"
    gi.write_text("my-custom-rules\n")
    backend = FilesBackend(base_dir=str(tmp_path), write_gitignore=True)
    backend.upsert(Envelope(id="a", content="hello"))
    assert gi.read_text() == "my-custom-rules\n"


# ------------------------------------------------------------------
# Real git integration
# ------------------------------------------------------------------


@pytest.mark.skipif(
    shutil.which("git") is None,
    reason="git not installed",
)
def test_git_check_ignore_private_ignored_public_tracked(tmp_path) -> None:
    """In a real git repo, private shards are ignored and public shards are tracked."""
    # Initialise a git repo inside tmp_path
    subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "test@test.com"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
    )

    backend = FilesBackend(base_dir=str(tmp_path), write_gitignore=True)
    backend.upsert(Envelope(id="priv", content="secret", scope=Scope("myapp", "private")))
    backend.upsert(Envelope(id="pub", content="hello", scope=Scope("myapp", "public")))

    private_file = tmp_path / "myapp__private.jsonl"
    public_file = tmp_path / "myapp__public.jsonl"
    sidecar = tmp_path / "foo__index.bin"
    sidecar.write_text("sidecar")

    # Private shard is ignored
    result = subprocess.run(
        ["git", "check-ignore", "-q", str(private_file)],
        cwd=tmp_path,
        capture_output=True,
    )
    assert result.returncode == 0, "private shard should be ignored"

    # Arbitrary non-public sidecar is ignored
    result = subprocess.run(
        ["git", "check-ignore", "-q", str(sidecar)],
        cwd=tmp_path,
        capture_output=True,
    )
    assert result.returncode == 0, "non-public sidecar should be ignored"

    # Public shard is NOT ignored
    result = subprocess.run(
        ["git", "check-ignore", "-q", str(public_file)],
        cwd=tmp_path,
        capture_output=True,
    )
    assert result.returncode != 0, "public shard should NOT be ignored"


# ------------------------------------------------------------------
# Factory / store.put forwarding
# ------------------------------------------------------------------


def test_build_forwards_write_gitignore(tmp_path) -> None:
    """build(base_dir=..., write_gitignore=True) returns a backend that honours the flag."""
    backend = build(base_dir=str(tmp_path), write_gitignore=True)
    assert isinstance(backend, FilesBackend)
    backend.upsert(Envelope(id="a", content="hello"))
    assert (tmp_path / ".gitignore").exists()


def test_store_put_forwards_write_gitignore(tmp_path) -> None:
    """store.put(..., backend='files', write_gitignore=True) materialises .gitignore."""
    store.put(
        Envelope(id="a", content="hello"),
        backend="files",
        base_dir=str(tmp_path),
        write_gitignore=True,
    )
    assert (tmp_path / ".gitignore").exists()
    assert (tmp_path / ".gitignore").read_text() == _GITIGNORE_CONTENT
