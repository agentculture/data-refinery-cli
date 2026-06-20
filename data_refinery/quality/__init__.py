"""data-refinery's consumer-agnostic data-quality checks.

Importable as a library (``data_refinery.quality``) and mirrored by the CLI verbs
``validate`` / ``dedup`` / ``integrity`` / ``freshness`` over one implementation.
The checks operate on storage-neutral envelopes and report **facts** — they never
rank, score, or interpret a document as a memory.
"""

from __future__ import annotations

from data_refinery.quality.checks import (
    dedup,
    find_duplicate_groups,
    freshness,
    integrity,
    validate_many,
    validate_payload,
)

__all__ = [
    "validate_payload",
    "validate_many",
    "find_duplicate_groups",
    "dedup",
    "integrity",
    "freshness",
]
