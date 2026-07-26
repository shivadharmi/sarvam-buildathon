"""Disk cache for digitised documents.

This is not an optimisation. Digitisation is the slow, paid, network-dependent
step, and the cache is what makes the demo survive a dead API -- it is the
offline fallback named in IDEA_SCOPE §5. It also keeps iteration free.

Repeatability comes from here, not from the model's `seed` (which is
best-effort only).
"""

from __future__ import annotations

import json
import unicodedata
from datetime import datetime, timezone
from pathlib import Path

from .config import CACHE_DIR
from .models import Block, DigitisedDoc
from .tables import flatten_tables


def _path_for(doc_id: str) -> Path:
    if not doc_id or "/" in doc_id or doc_id.startswith("."):
        raise ValueError(f"unsafe doc_id: {doc_id!r}")
    return CACHE_DIR / f"{doc_id}.json"


def save(doc: DigitisedDoc) -> Path:
    """Write a digitised document to the cache and return its path."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    path = _path_for(doc.doc_id)
    path.write_text(doc.model_dump_json(indent=2), encoding="utf-8")
    return path


def load(doc_id: str) -> DigitisedDoc | None:
    """Return the cached document, or None if it has not been digitised."""
    path = _path_for(doc_id)
    if not path.exists():
        return None
    return DigitisedDoc.model_validate_json(path.read_text(encoding="utf-8"))


def list_cached() -> list[DigitisedDoc]:
    """Every cached document, oldest first."""
    if not CACHE_DIR.exists():
        return []
    docs = [
        DigitisedDoc.model_validate_json(p.read_text(encoding="utf-8"))
        for p in sorted(CACHE_DIR.glob("*.json"))
    ]
    return sorted(docs, key=lambda d: d.digitised_at)


BLOCK_SEPARATOR = "\n\n"


def build_doc(
    *,
    doc_id: str,
    language: str,
    raw_blocks: list[dict],
    source_filename: str,
    page_count: int = 1,
) -> DigitisedDoc:
    """Assemble page blocks into the canonical document we store.

    NFC is applied exactly once, here, and per block *before* offsets are
    computed -- normalising the joined string afterwards could shift every
    offset and silently misalign highlights.
    """
    blocks: list[Block] = []
    parts: list[str] = []
    cursor = 0

    for raw in sorted(raw_blocks, key=lambda b: b.get("reading_order", 0)):
        # Tables first: the digitiser puts one cell per line, which would make
        # a cited line read `<td>09</td>` with nothing to say what it counts.
        text = unicodedata.normalize("NFC", flatten_tables(raw.get("text", "")))
        if not text.strip():
            continue

        coords = raw.get("coordinates", {})
        blocks.append(
            Block(
                reading_order=raw.get("reading_order", len(blocks) + 1),
                layout_tag=raw.get("layout_tag", "unknown"),
                confidence=raw.get("confidence", 0.0),
                text=text,
                x1=coords.get("x1", 0.0),
                y1=coords.get("y1", 0.0),
                x2=coords.get("x2", 0.0),
                y2=coords.get("y2", 0.0),
                start=cursor,
                end=cursor + len(text),
            )
        )
        parts.append(text)
        cursor += len(text) + len(BLOCK_SEPARATOR)

    return DigitisedDoc(
        doc_id=doc_id,
        language=language,
        text=BLOCK_SEPARATOR.join(parts),
        source_filename=source_filename,
        digitised_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        page_count=page_count,
        blocks=tuple(blocks),
    )
