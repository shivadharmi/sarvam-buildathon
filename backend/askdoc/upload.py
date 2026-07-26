"""Accepting a reader's own page -- everything that happens before we pay.

Digitisation is the slow, paid, rate-limited step (10 requests/minute). Every
rule in this module is here so a file that was never going to work is refused
in milliseconds instead of costing a call and a minute of the demo's budget.

Two things are load-bearing:

* **The bytes decide the type, never the name.** The extension and the
  browser's `Content-Type` are the reader's claim about the file; the magic
  bytes are the file. A JPEG called `scan.pdf` is a JPEG.
* **The size ceiling is enforced while streaming.** Reading the body into
  memory and measuring it afterwards would turn every oversized upload into a
  memory-exhaustion lever, so the write is abandoned the moment it crosses.
"""

from __future__ import annotations

import hashlib
import os
import tempfile
from pathlib import Path
from typing import Protocol

from pydantic import ConfigDict

from .config import MAX_PAGES, MAX_UPLOAD_BYTES, MIN_UPLOAD_BYTES, UPLOADS_DIR
from .models import Frozen

# Read granularity. Also the slack in the size ceiling: we can only notice an
# overrun on a chunk boundary, so at most one chunk beyond the limit is ever
# touched.
CHUNK_BYTES = 64 * 1024

# Enough for the longest signature we check (PNG's is 8 bytes), so the decision
# is made once from a fixed-width prefix rather than growing with the file.
_MAGIC_PREFIX_BYTES = 8

_SIGNATURES: tuple[tuple[bytes, str], ...] = (
    (b"%PDF-", "pdf"),
    (b"\x89PNG\r\n\x1a\n", "png"),
    (b"\xff\xd8\xff", "jpeg"),
)

# --- product copy ------------------------------------------------------------
#
# These are shown to the reader verbatim -- api.py passes `.message` straight
# through. They are copy, not diagnostics: say what we can take and what to do
# next, and never imply the file is at fault when the limit is ours.

UNSUPPORTED_TYPE = "I can read PDF, PNG and JPEG pages. This file looks like something else."
EMPTY_FILE = "That file is empty."
# Deliberately not the same as EMPTY_FILE: nothing arrived is a different
# situation to the reader than something arrived that cannot be a document.
TOO_SMALL = "That file is too small to be a page. Try uploading the original scan or photo."
DAMAGED_PDF = "I couldn't open this PDF — it may be damaged."


class UploadRejected(ValueError):
    """The file cannot be read. `.message` is shown to the reader verbatim."""

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


class ByteStream(Protocol):
    """Anything with a blocking `read(n)` -- notably `UploadFile.file`."""

    def read(self, size: int) -> bytes: ...


class StoredUpload(Frozen):
    """A validated file on disk, ready for its first (and only) paid call."""

    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    doc_id: str
    path: Path
    kind: str
    size_bytes: int
    page_count: int
    source_filename: str


def sniff(head: bytes) -> str | None:
    """Identify the file from its leading bytes, or None if we cannot read it.

    Deliberately a whitelist of exact signatures. The alternative -- believing
    the extension -- lets a reader hand us anything and have it labelled a PDF.
    """
    return next((kind for magic, kind in _SIGNATURES if head.startswith(magic)), None)


def count_pdf_pages(path: Path) -> int:
    """Pages in a PDF, or raise `UploadRejected` if it cannot be opened.

    A file that starts `%PDF-` still may not be one, and a PDF with no pages
    has nothing on it to answer from; both are the same thing to the reader.
    """
    from pypdf import PdfReader  # imported lazily: only uploads need it

    try:
        pages = len(PdfReader(str(path)).pages)
    except Exception as exc:  # pypdf raises a wide family of parse errors
        raise UploadRejected(DAMAGED_PDF) from exc

    if pages < 1:
        raise UploadRejected(DAMAGED_PDF)
    return pages


def _human_size(size_bytes: int) -> str:
    mb = size_bytes / (1024 * 1024)
    if mb >= 10:
        return f"{mb:.0f} MB"
    if mb >= 1:
        return f"{mb:.1f} MB"
    kb = size_bytes / 1024
    return f"{kb:.0f} KB" if kb >= 1 else f"{size_bytes} bytes"


def _too_big(size_bytes: int | None) -> str:
    limit = _human_size(MAX_UPLOAD_BYTES)
    # Aborting mid-stream means we genuinely do not know how big the file was,
    # and inventing a number would be worse copy than admitting we stopped.
    if size_bytes is None:
        return f"That file is too big. I can take up to {limit}."
    return f"That file is {_human_size(size_bytes)}. I can take up to {limit}."


def _too_many_pages(pages: int) -> str:
    return (
        f"This PDF has {pages} pages. "
        f"I can read up to {MAX_PAGES} at a time — try splitting it."
    )


def _basename(filename: str) -> str:
    """The reader's filename, stripped to a leaf. Metadata only, never a path."""
    return Path(filename.replace("\\", "/")).name or "upload"


def store_upload(
    stream: ByteStream,
    *,
    filename: str,
    declared_bytes: int | None = None,
) -> StoredUpload:
    """Validate an uploaded file and land it in `UPLOADS_DIR`.

    `declared_bytes` (the browser's `Content-Length`) is advisory and used in
    one direction only: it can refuse a file before a byte is read, never admit
    one. A client that understates its size still meets the streamed ceiling.

    The final name is `<doc_id>.<kind>`, and `doc_id` is derived from the
    content: the same page uploaded twice is the same document, which makes a
    re-upload a free cache hit rather than a second paid digitisation.
    """
    if declared_bytes is not None and declared_bytes > MAX_UPLOAD_BYTES:
        raise UploadRejected(_too_big(declared_bytes))

    UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
    handle = tempfile.NamedTemporaryFile(dir=UPLOADS_DIR, suffix=".part", delete=False)
    temp_path = Path(handle.name)

    try:
        digest = hashlib.sha256()
        head = b""
        size = 0
        kind: str | None = None

        with handle:
            while chunk := stream.read(CHUNK_BYTES):
                size += len(chunk)
                if size > MAX_UPLOAD_BYTES:
                    raise UploadRejected(_too_big(declared_bytes))

                # Decide the type as soon as the prefix is complete, so an
                # unreadable file is refused after one chunk rather than after
                # 25 MB of writing.
                if kind is None and len(head) < _MAGIC_PREFIX_BYTES:
                    head += chunk[: _MAGIC_PREFIX_BYTES - len(head)]
                    if len(head) == _MAGIC_PREFIX_BYTES:
                        kind = sniff(head)
                        if kind is None:
                            raise UploadRejected(UNSUPPORTED_TYPE)

                digest.update(chunk)
                handle.write(chunk)

        if size == 0:
            raise UploadRejected(EMPTY_FILE)

        if kind is None:  # a file shorter than the prefix never reached the check
            kind = sniff(head)
            if kind is None:
                raise UploadRejected(UNSUPPORTED_TYPE)

        # After the sniff on purpose: a 200-byte text file is more usefully
        # told it is the wrong type than told it is short.
        if size < MIN_UPLOAD_BYTES:
            raise UploadRejected(TOO_SMALL)

        page_count = count_pdf_pages(temp_path) if kind == "pdf" else 1
        if page_count > MAX_PAGES:
            # Rejected, never truncated. Answering from the first ten pages
            # would make "not stated" mean "not stated in the part I read" --
            # a different claim, and one the reader cannot tell apart.
            raise UploadRejected(_too_many_pages(page_count))

        doc_id = f"up_{digest.hexdigest()[:16]}"
        final_path = UPLOADS_DIR / f"{doc_id}.{kind}"
        os.replace(temp_path, final_path)

        return StoredUpload(
            doc_id=doc_id,
            path=final_path,
            kind=kind,
            size_bytes=size,
            page_count=page_count,
            source_filename=_basename(filename),
        )
    finally:
        # Every rejection exits mid-write, so cleanup cannot sit on the happy
        # path. After the rename there is nothing left here to remove.
        temp_path.unlink(missing_ok=True)
