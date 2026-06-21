"""Files store backend — dependency-free JSONL persistence (the default).

Persists envelopes as JSON Lines, one file per scope
(``<scope-name>__<visibility>.jsonl``) under ``DR_DATA_DIR`` (default
``~/.data-refinery/store``). Uses only the standard library, so it keeps the
``dependencies = []`` invariant and is always available.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Callable, get_args

from data_refinery.cli._errors import EXIT_ENV_ERROR, EXIT_USER_ERROR, CliError
from data_refinery.store.backend import Backend
from data_refinery.store.envelope import Envelope, Scope, Visibility, can_serve

_ENV_DIR = "DR_DATA_DIR"
_JSONL_GLOB = "*.jsonl"  # one scope file per (name, visibility)
_TMP_SUFFIX = ".tmp"  # atomic-write temp sibling: "<scope>.jsonl.tmp"
# Re-derived from the public `Visibility` type so it never drifts from it.
_VISIBILITIES: tuple[str, ...] = get_args(Visibility)

# A consumer-supplied converter: one decoded legacy line -> an Envelope (or None
# to drop the record). The consumer owns its legacy schema; data-refinery never
# imports it. ``None`` (in place of a transform) means "self-canonicalise".
Transform = Callable[[dict[str, Any]], Envelope | None]


class FilesBackend:
    """Persist envelopes as JSONL files, one file per scope."""

    def __init__(self, base_dir: str | None = None) -> None:
        if base_dir is None:
            base_dir = os.environ.get(_ENV_DIR) or str(Path.home() / ".data-refinery" / "store")
        self._base = Path(base_dir)
        self._base.mkdir(parents=True, exist_ok=True)

    # -- Backend protocol -----------------------------------------------

    def upsert(self, envelope: Envelope) -> None:
        """Insert or replace *envelope* idempotently (by id; dedup by hash on insert)."""
        path = self._scope_file(envelope.scope)
        records = self._load(path)

        replaced = False
        for i, r in enumerate(records):
            if r.id == envelope.id:
                records[i] = envelope
                replaced = True
                break
        if not replaced:
            # Dedup by hash: drop any existing record with the same content hash
            # so re-putting identical content under a new id never duplicates.
            records = [r for r in records if r.hash != envelope.hash]
            records.append(envelope)

        self._save(path, records)

    def get(self, id: str, scope: Scope) -> Envelope | None:
        """Return the envelope with *id* visible to *scope*, or None."""
        for env in self._visible(scope):
            if env.id == id:
                return env
        return None

    def list(self, scope: Scope) -> list[Envelope]:
        """List every envelope visible to *scope* (can_serve-filtered)."""
        return self._visible(scope)

    def all(self) -> list[Envelope]:
        """Enumerate every stored envelope across all scopes (no filtering)."""
        out: list[Envelope] = []
        for path in sorted(self._base.glob(_JSONL_GLOB)):
            out.extend(self._load(path))
        return out

    def delete(self, id: str) -> bool:
        """Hard-delete every envelope with *id*. Returns True if any were removed."""
        removed = False
        for path in sorted(self._base.glob(_JSONL_GLOB)):
            records = self._load(path)
            kept = [r for r in records if r.id != id]
            if len(kept) != len(records):
                self._save(path, kept)
                removed = True
        return removed

    # -- migration -------------------------------------------------------

    def migrate(
        self, transform: Transform | None = None, *, dry_run: bool = False
    ) -> dict[str, Any]:
        """Rewrite every scope file through *transform*, atomically per file.

        With ``transform=None`` this re-canonicalises data-refinery's **own**
        Envelope-JSONL: re-validate every line, re-fill a missing hash, normalise
        the on-disk form (the self-heal / format-version path the ``store
        migrate`` CLI verb uses). With a *transform* the consumer converts each
        decoded legacy line into an :class:`Envelope` (return ``None`` to drop a
        record); the consumer supplies only the transform — never a write path.

        The rewrite is **atomic per file** (a temp sibling + ``os.replace``) and
        **idempotent**: a file whose canonical re-serialisation already equals
        its current bytes is left untouched, so a second run rewrites nothing. An
        interrupted run leaves either the old or the new file intact (never a
        partial file) and is safe to resume. Returns a summary dict.
        """
        root = self._base.resolve()  # canonicalise once; harden the write sink
        migrated: list[str] = []
        skipped = 0
        files = 0
        for path in sorted(root.glob(_JSONL_GLOB)):
            files += 1
            self._assert_contained(path, root)
            original = path.read_text(encoding="utf-8")
            new_text = _serialize(self._migrate_lines(original, transform, path))
            if new_text == original:
                skipped += 1
                continue
            migrated.append(path.name)
            if not dry_run:
                self._atomic_write(path, new_text)
        self._reap_orphan_tmp(root)
        return {
            "backend": "files",
            "files": files,
            "migrated": len(migrated),
            "migrated_files": migrated,
            "skipped": skipped,
            "dry_run": dry_run,
        }

    def _migrate_lines(self, text: str, transform: Transform | None, path: Path) -> list[Envelope]:
        out: list[Envelope] = []
        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError as exc:
                raise CliError(
                    code=EXIT_ENV_ERROR,
                    message=f"corrupt line in {path.name}: {exc}",
                    remediation=f"remove or repair the corrupt line in {path}",
                ) from exc
            env = _to_envelope(obj, transform)
            if env is None:  # transform dropped the record (e.g. a tombstone)
                continue
            out.append(_validate(env))
        return out

    @staticmethod
    def _assert_contained(path: Path, root: Path) -> None:
        """Refuse a scope file that resolves outside the canonical store root.

        ``glob`` already constrains the listing to *root*, but a symlinked scope
        file could still point elsewhere; resolving and containment-checking each
        path keeps the write sink reasoning against an owner-controlled root (not
        an attacker-reachable target) — the defensible posture for the component
        that *owns* the storage layout.
        """
        resolved = path.resolve()
        try:
            contained = os.path.commonpath([str(resolved), str(root)]) == str(root)
        except ValueError:  # different drives / mixed roots
            contained = False
        if not contained:
            raise CliError(
                code=EXIT_ENV_ERROR,
                message=f"{path.name} resolves outside the store root {root}",
                remediation="remove the symlink or point DR_DATA_DIR at the real store directory",
            )

    @staticmethod
    def _reap_orphan_tmp(root: Path) -> None:
        """Remove ``*.jsonl.tmp`` left by a prior interrupted rewrite.

        ``os.replace`` consumes the temp on success, so a surviving temp is the
        residue of a crash *before* the swap — the real file is intact. Reaping
        keeps the store dir tidy and the ``*.jsonl`` glob unambiguous.
        """
        for tmp in root.glob(_JSONL_GLOB + _TMP_SUFFIX):
            try:
                tmp.unlink()
            except OSError:  # pragma: no cover - best effort
                pass

    # -- internal helpers ------------------------------------------------

    def _visible(self, scope: Scope) -> list[Envelope]:
        out: list[Envelope] = []
        for path in sorted(self._base.glob(_JSONL_GLOB)):
            for env in self._load(path):
                if can_serve(scope, env.scope):
                    out.append(env)
        return out

    def _scope_file(self, scope: Scope) -> Path:
        safe = scope.name.replace("/", "_").replace("\\", "_")
        return self._base / f"{safe}__{scope.visibility}.jsonl"

    def _load(self, path: Path) -> list[Envelope]:
        if not path.exists():
            return []
        out: list[Envelope] = []
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                out.append(Envelope.from_dict(json.loads(line)))
            except (json.JSONDecodeError, KeyError) as exc:
                raise CliError(
                    code=EXIT_ENV_ERROR,
                    message=f"corrupt line in {path.name}: {exc}",
                    remediation=f"remove or repair the corrupt line in {path}",
                ) from exc
        return out

    def _save(self, path: Path, records: list[Envelope]) -> None:
        self._atomic_write(path, _serialize(records))

    def _atomic_write(self, path: Path, text: str) -> None:
        """Write *text* to *path* atomically (temp sibling + ``os.replace``).

        The temp is a sibling in the same directory, so ``os.replace`` is a
        same-filesystem atomic rename: a crash leaves either the old file or the
        new one — never a half-written file. Shared by ``upsert``/``delete`` and
        the migration rewrite, so every write to a scope file is durable.
        """
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(path.name + _TMP_SUFFIX)
        try:
            tmp.write_text(text, encoding="utf-8")
            os.replace(tmp, path)
        except OSError:
            try:
                tmp.unlink()
            except OSError:  # pragma: no cover - best effort cleanup
                pass
            raise


def _serialize(records: list[Envelope]) -> str:
    """Canonical Envelope-JSONL: one ``to_dict()`` per line, trailing newline."""
    return "".join(json.dumps(r.to_dict()) + "\n" for r in records)


def _validate(env: Envelope) -> Envelope:
    """Fail closed on an envelope whose scope visibility is unrecognised.

    The no-leak invariant (:func:`can_serve`) only holds for a known visibility;
    a transform that produced an unknown one must abort the migration **before**
    any write rather than persist an unservable record.
    """
    if env.scope.visibility not in _VISIBILITIES:
        raise CliError(
            code=EXIT_USER_ERROR,
            message=(
                f"transformed envelope {env.id!r} has unknown "
                f"scope.visibility {env.scope.visibility!r}"
            ),
            remediation='the transform must set scope.visibility to "public" or "private"',
        )
    return env


def _to_envelope(obj: object, transform: Transform | None) -> Envelope | None:
    """Map one decoded line to an Envelope (or None to drop it).

    ``transform=None`` self-canonicalises (every line is already data-refinery's
    own form). With a *transform*, an already-canonical line is kept **verbatim**
    so a re-run never re-applies the consumer's transform to migrated data — that
    is what makes a second run a byte-for-byte no-op without data-refinery ever
    knowing the consumer's legacy schema.
    """
    if transform is None:
        return Envelope.from_dict(obj)  # type: ignore[arg-type]
    if isinstance(obj, dict):
        try:
            already = Envelope.from_dict(obj)
        except (KeyError, TypeError, AttributeError, ValueError, CliError):
            already = None
        if already is not None and already.to_dict() == obj:
            return already
    return transform(obj)  # type: ignore[arg-type]


def build(**_kwargs: object) -> Backend:
    """Factory: a default FilesBackend (ignores kwargs like ``timeout_ms``)."""
    return FilesBackend()
