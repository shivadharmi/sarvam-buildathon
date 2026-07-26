"""Sarvam Document Digitisation -- the scored capability.

Uses the SDK here (unlike chat, which goes direct) because it genuinely
collapses a multi-step async job into five calls.

Every result is cached to disk. Digitisation is slow, paid, and the single
network dependency the demo cannot survive losing, so nothing in this module
should ever run twice for the same document.
"""

from __future__ import annotations

import json
import tempfile
import zipfile
from pathlib import Path

from sarvamai import SarvamAI

from . import cache
from .config import (
    DIGITISE_OUTPUT_FORMAT,
    DIGITISE_TIMEOUT_S,
    api_key,
)
from .models import DigitisedDoc, DocOrigin, LanguageSource

# Anything other than these two means the output is incomplete or absent.
# PartiallyCompleted is explicitly NOT success.
_SUCCESS_STATES = {"Completed"}


class DigitisationError(RuntimeError):
    """Digitisation did not produce usable text."""


def _client() -> SarvamAI:
    return SarvamAI(api_subscription_key=api_key())


def _extract_blocks(zip_path: Path) -> tuple[list[dict], int]:
    """Pull page-level blocks out of the downloaded ZIP.

    The ZIP holds `document.md` and `metadata/page_NNN.json`. We use the JSON,
    not the Markdown: the Markdown renumbers every wrapped line as a fresh list
    item, which injects markers like "26. " into the middle of sentences and
    makes genuinely verbatim quotes impossible to match. The JSON preserves the
    page's own numbering and carries coordinates and layout tags besides.
    """
    with zipfile.ZipFile(zip_path) as archive:
        pages = sorted(
            n for n in archive.namelist()
            if n.lower().endswith(".json") and not n.endswith("/")
        )
        if not pages:
            names = archive.namelist()
            raise DigitisationError(f"No page JSON in ZIP. Members: {names}")

        blocks: list[dict] = []
        for offset, name in enumerate(pages):
            page = json.loads(archive.read(name))
            for block in page.get("blocks", []):
                # Keep pages in order by biasing each page's reading order.
                block = {**block, "reading_order": offset * 1000 + block.get("reading_order", 0)}
                blocks.append(block)

    if not blocks:
        raise DigitisationError("Digitisation returned no text blocks.")

    return blocks, len(pages)


def digitise(
    source_path: Path | str,
    *,
    language: str,
    doc_id: str,
    force: bool = False,
    persist: bool = True,
    origin: DocOrigin = DocOrigin.BUILTIN,
    label: str = "",
    language_source: LanguageSource = LanguageSource.BUILTIN,
    probe_language: str = "",
) -> DigitisedDoc:
    """Digitise a page and cache it. Returns the cached copy when one exists.

    `force=True` re-runs against the live API, which costs money -- reserve it
    for when the cached text is genuinely wrong.

    `persist=False` neither reads nor writes the cache. That is for the
    ingestion probe pass, which reads a page in a language we have only guessed
    at: it is a paid call worth keeping in hand, but not a document, and
    caching it would put text we already suspect is garbled in the library
    under the same name the real reading will want.

    The provenance arguments are passed straight through to `cache.build_doc`.
    They record how this document arrived and how its language was decided --
    a reader who can see we guessed can correct us.
    """
    if not force and persist:
        cached = cache.load(doc_id)
        if cached is not None:
            return cached

    source = Path(source_path)
    if not source.exists():
        raise DigitisationError(f"No such file: {source}")

    job = _client().document_intelligence.create_job(
        language=language,
        output_format=DIGITISE_OUTPUT_FORMAT,
    )
    job.upload_file(str(source))
    job.start()
    status = job.wait_until_complete(timeout=DIGITISE_TIMEOUT_S)

    state = getattr(status, "job_state", None) or getattr(status, "status", None)
    if state not in _SUCCESS_STATES:
        raise DigitisationError(
            f"Digitisation finished in state {state!r} (not Completed). "
            f"PartiallyCompleted and Failed both mean the text is unreliable."
        )

    with tempfile.TemporaryDirectory() as tmp:
        zip_path = Path(tmp) / "output.zip"
        job.download_output(str(zip_path))
        raw_blocks, page_count = _extract_blocks(zip_path)

    doc = cache.build_doc(
        doc_id=doc_id,
        language=language,
        raw_blocks=raw_blocks,
        source_filename=source.name,
        page_count=page_count,
        origin=origin,
        label=label,
        language_source=language_source,
        probe_language=probe_language,
    )

    if not doc.text.strip():
        # Raised rather than cached. A document with no text answers "not
        # stated" to everything the page states, which is exactly the
        # dishonesty this product exists to prevent.
        raise DigitisationError("Digitisation produced empty text.")

    if persist:
        cache.save(doc)
    return doc
