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

from data_refinery.cli._errors import EXIT_ENV_ERROR, CliError
from data_refinery.store.backend import Backend
from data_refinery.store.envelope import Envelope, Scope, can_serve

_ENV_DIR = "DR_DATA_DIR"


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
        for path in sorted(self._base.glob("*.jsonl")):
            out.extend(self._load(path))
        return out

    def delete(self, id: str) -> bool:
        """Hard-delete every envelope with *id*. Returns True if any were removed."""
        removed = False
        for path in sorted(self._base.glob("*.jsonl")):
            records = self._load(path)
            kept = [r for r in records if r.id != id]
            if len(kept) != len(records):
                self._save(path, kept)
                removed = True
        return removed

    # -- internal helpers ------------------------------------------------

    def _visible(self, scope: Scope) -> list[Envelope]:
        out: list[Envelope] = []
        for path in sorted(self._base.glob("*.jsonl")):
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
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            for r in records:
                f.write(json.dumps(r.to_dict()) + "\n")


def build(**_kwargs: object) -> Backend:
    """Factory: a default FilesBackend (ignores kwargs like ``timeout_ms``)."""
    return FilesBackend()
