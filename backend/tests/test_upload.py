"""Validation happens here or it happens on Sarvam's bill.

Every rejection in this file is one digitisation call (paid, 10/min) that never
had to be made. The rules are also the last place the reader's own bytes are
trusted: what the browser calls the file is advisory, what the bytes say is not.
"""

import io

import pytest
from pypdf import PdfWriter

from askdoc import upload
from askdoc.upload import UploadRejected

# A real 1x1 PNG and a JPEG with the right SOI marker. Sniffing only reads the
# first bytes, but building genuine files keeps the fixtures honest.
PNG_BYTES = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01"
    b"\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
)
JPEG_BYTES = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00" + b"\xff\xd9"


# A blank one-page PDF is ~430 bytes and a 1x1 PNG ~70, both under the
# plausibility floor. Real pages are megabytes, so the fixtures are padded to
# clear it -- as metadata for PDFs, which keeps them genuinely parseable, and
# as trailing bytes for images, which nothing here decodes.
_PAD = 2048


def pdf_bytes(pages: int = 1, pad: int = _PAD) -> bytes:
    writer = PdfWriter()
    for _ in range(pages):
        writer.add_blank_page(width=72, height=72)
    if pad:
        writer.add_metadata({"/Title": "x" * pad})
    buffer = io.BytesIO()
    writer.write(buffer)
    return buffer.getvalue()


def png_page(pad: int = _PAD) -> bytes:
    return PNG_BYTES + b"\x00" * pad


def jpeg_page(pad: int = _PAD) -> bytes:
    return JPEG_BYTES + b"\x00" * pad


class CountingStream:
    """A stream that remembers how much of itself was actually read.

    The point of the size check is that an oversized body is abandoned rather
    than consumed; that is only observable from the producer's side.
    """

    def __init__(self, data: bytes):
        self._inner = io.BytesIO(data)
        self.bytes_read = 0

    def read(self, size: int) -> bytes:
        chunk = self._inner.read(size)
        self.bytes_read += len(chunk)
        return chunk


@pytest.fixture(autouse=True)
def isolated_uploads_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(upload, "UPLOADS_DIR", tmp_path)
    return tmp_path


def store(data: bytes, filename: str = "page.pdf", **kwargs):
    return upload.store_upload(io.BytesIO(data), filename=filename, **kwargs)


class TestSniff:
    def test_recognises_a_pdf(self):
        assert upload.sniff(pdf_bytes()[:8]) == "pdf"

    def test_recognises_a_png(self):
        assert upload.sniff(PNG_BYTES[:8]) == "png"

    def test_recognises_a_jpeg(self):
        assert upload.sniff(JPEG_BYTES[:8]) == "jpeg"

    @pytest.mark.parametrize(
        "head",
        [b"", b"GIF89a\x01\x00", b"PK\x03\x04\x14\x00\x00\x00", b"<!DOCTYPE html>"],
    )
    def test_anything_else_is_unknown(self, head):
        assert upload.sniff(head) is None

    def test_a_truncated_png_header_is_not_a_png(self):
        # The signature exists precisely to catch files that merely start right.
        assert upload.sniff(b"\x89PNG\r\n") is None


class TestTypeIsDecidedByBytes:
    def test_a_jpeg_renamed_pdf_is_stored_as_a_jpeg(self):
        # The whole reason we sniff: a wrong extension must not decide anything.
        stored = store(jpeg_page(), filename="scan.pdf")
        assert stored.kind == "jpeg"
        assert stored.path.suffix == ".jpeg"
        assert stored.page_count == 1

    def test_a_pdf_renamed_png_is_still_page_counted(self):
        stored = store(pdf_bytes(3), filename="notice.png")
        assert stored.kind == "pdf"
        assert stored.page_count == 3

    def test_an_unsupported_type_is_rejected(self):
        with pytest.raises(UploadRejected) as excinfo:
            store(b"GIF89a" + b"\x00" * 100, filename="page.pdf")
        assert excinfo.value.message == (
            "I can read PDF, PNG and JPEG pages. This file looks like something else."
        )

    def test_a_rejected_upload_leaves_nothing_on_disk(self, isolated_uploads_dir):
        with pytest.raises(UploadRejected):
            store(b"GIF89a" + b"\x00" * 100)
        assert list(isolated_uploads_dir.iterdir()) == []


class TestReadability:
    def test_a_zero_byte_file_is_rejected(self):
        with pytest.raises(UploadRejected) as excinfo:
            store(b"")
        assert excinfo.value.message == "That file is empty."

    def test_a_corrupt_pdf_is_rejected(self):
        with pytest.raises(UploadRejected) as excinfo:
            store(b"%PDF-1.7\nthis is not actually a pdf\n" + b"\x00" * 2048)
        assert excinfo.value.message == "I couldn't open this PDF — it may be damaged."

    def test_a_corrupt_pdf_leaves_nothing_on_disk(self, isolated_uploads_dir):
        with pytest.raises(UploadRejected):
            store(b"%PDF-1.7\nthis is not actually a pdf\n" + b"\x00" * 2048)
        assert list(isolated_uploads_dir.iterdir()) == []

    def test_a_pdf_with_no_pages_is_rejected(self):
        # Structurally valid, and there is nothing on it to answer from --
        # indistinguishable from damaged as far as the reader is concerned.
        with pytest.raises(UploadRejected) as excinfo:
            store(pdf_bytes(0))
        assert excinfo.value.message == "I couldn't open this PDF — it may be damaged."

    def test_a_file_too_short_to_sniff_is_rejected(self):
        with pytest.raises(UploadRejected) as excinfo:
            store(b"hi", filename="page.pdf")
        assert excinfo.value.message == (
            "I can read PDF, PNG and JPEG pages. This file looks like something else."
        )

    def test_a_file_shorter_than_the_prefix_is_still_sniffed(self):
        # JPEG's signature is 3 bytes, so a file that ends before the 8-byte
        # prefix is complete must still get sniffed rather than fall through
        # unidentified. It is refused for being tiny, not for being unreadable.
        with pytest.raises(UploadRejected) as excinfo:
            store(b"\xff\xd8\xff", filename="tiny.jpg")
        assert excinfo.value.message == upload.TOO_SMALL

    def test_count_pdf_pages_reads_the_real_count(self, tmp_path):
        path = tmp_path / "four.pdf"
        path.write_bytes(pdf_bytes(4))
        assert upload.count_pdf_pages(path) == 4


class TestPageCeiling:
    def test_exactly_the_limit_is_accepted(self):
        stored = store(pdf_bytes(upload.MAX_PAGES))
        assert stored.page_count == upload.MAX_PAGES

    def test_one_page_over_the_limit_is_rejected(self):
        with pytest.raises(UploadRejected) as excinfo:
            store(pdf_bytes(upload.MAX_PAGES + 1))
        assert excinfo.value.message == (
            f"This PDF has {upload.MAX_PAGES + 1} pages. "
            f"I can read up to {upload.MAX_PAGES} at a time — try splitting it."
        )

    def test_an_over_long_pdf_is_never_truncated(self, isolated_uploads_dir):
        # Reading the first 10 pages and answering from them would turn "not
        # stated" into "not stated in the part I read" -- a different claim,
        # and one the reader has no way to tell apart. Refuse instead.
        with pytest.raises(UploadRejected):
            store(pdf_bytes(upload.MAX_PAGES + 5))
        assert list(isolated_uploads_dir.iterdir()) == []


class TestSizeFloor:
    def test_just_under_the_floor_is_rejected(self):
        with pytest.raises(UploadRejected) as excinfo:
            store(jpeg_page(pad=upload.MIN_UPLOAD_BYTES - len(JPEG_BYTES) - 1), filename="a.jpg")
        assert excinfo.value.message == (
            "That file is too small to be a page. Try uploading the original scan or photo."
        )

    def test_exactly_the_floor_is_accepted(self):
        stored = store(jpeg_page(pad=upload.MIN_UPLOAD_BYTES - len(JPEG_BYTES)), filename="a.jpg")
        assert stored.size_bytes == upload.MIN_UPLOAD_BYTES

    def test_a_zero_byte_file_is_not_reported_as_merely_small(self):
        # Nothing arrived and something-that-cannot-be-a-page arrived are
        # different situations, and the reader acts on them differently.
        with pytest.raises(UploadRejected) as excinfo:
            store(b"")
        assert excinfo.value.message == upload.EMPTY_FILE
        assert upload.EMPTY_FILE != upload.TOO_SMALL

    def test_a_small_file_of_the_wrong_type_is_told_the_type_first(self):
        # Being told a text file is the wrong type is more useful than being
        # told it is short, which would send the reader off to find a bigger
        # copy of a file that was never going to work.
        with pytest.raises(UploadRejected) as excinfo:
            store(b"just some notes I typed", filename="page.pdf")
        assert excinfo.value.message == upload.UNSUPPORTED_TYPE

    def test_an_undersized_upload_leaves_nothing_on_disk(self, isolated_uploads_dir):
        with pytest.raises(UploadRejected):
            store(b"\xff\xd8\xff", filename="tiny.jpg")
        assert list(isolated_uploads_dir.iterdir()) == []


class TestSizeCeiling:
    def test_an_oversized_body_is_abandoned_mid_stream(self, monkeypatch):
        monkeypatch.setattr(upload, "MAX_UPLOAD_BYTES", 256 * 1024)
        stream = CountingStream(b"\xff\xd8\xff" + b"\x00" * (8 * 1024 * 1024))

        with pytest.raises(UploadRejected):
            upload.store_upload(stream, filename="huge.jpg")

        # Buffering the body and measuring it afterwards would make every
        # oversized upload a memory-exhaustion lever; we must stop early.
        assert stream.bytes_read <= upload.MAX_UPLOAD_BYTES + upload.CHUNK_BYTES

    def test_an_oversized_body_leaves_no_partial_file(self, monkeypatch, isolated_uploads_dir):
        monkeypatch.setattr(upload, "MAX_UPLOAD_BYTES", 256 * 1024)
        with pytest.raises(UploadRejected):
            store(b"\xff\xd8\xff" + b"\x00" * (2 * 1024 * 1024), filename="huge.jpg")
        assert list(isolated_uploads_dir.iterdir()) == []

    def test_the_message_names_both_sizes_when_the_size_is_known(self, monkeypatch):
        monkeypatch.setattr(upload, "MAX_UPLOAD_BYTES", 25 * 1024 * 1024)
        with pytest.raises(UploadRejected) as excinfo:
            store(jpeg_page(), filename="huge.jpg", declared_bytes=41 * 1024 * 1024)
        assert excinfo.value.message == "That file is 41 MB. I can take up to 25 MB."

    def test_the_message_admits_we_stopped_when_the_size_is_unknown(self, monkeypatch):
        # Aborting mid-stream means we never learned the real size. Inventing
        # a number would be worse copy than saying we stopped reading.
        monkeypatch.setattr(upload, "MAX_UPLOAD_BYTES", 2 * 1024 * 1024)
        with pytest.raises(UploadRejected) as excinfo:
            store(b"\xff\xd8\xff" + b"\x00" * (4 * 1024 * 1024), filename="huge.jpg")
        assert excinfo.value.message == "That file is too big. I can take up to 2.0 MB."

    def test_a_declared_oversize_is_rejected_without_reading_a_byte(self, monkeypatch):
        # Content-Length is not trusted to let a file *in*, only to refuse one
        # early. A client that overstates its own size only hurts itself.
        monkeypatch.setattr(upload, "MAX_UPLOAD_BYTES", 1024)
        stream = CountingStream(b"\xff\xd8\xff" + b"\x00" * 4096)
        with pytest.raises(UploadRejected):
            upload.store_upload(stream, filename="huge.jpg", declared_bytes=99999)
        assert stream.bytes_read == 0

    def test_a_lying_content_length_does_not_get_a_file_in(self, monkeypatch):
        monkeypatch.setattr(upload, "MAX_UPLOAD_BYTES", 1024)
        with pytest.raises(UploadRejected):
            store(b"\xff\xd8\xff" + b"\x00" * 4096, filename="small.jpg", declared_bytes=10)

    def test_a_file_at_exactly_the_ceiling_is_accepted(self, monkeypatch):
        limit = 4096
        monkeypatch.setattr(upload, "MAX_UPLOAD_BYTES", limit)
        stored = store(JPEG_BYTES + b"\x00" * (limit - len(JPEG_BYTES)), filename="edge.jpg")
        assert stored.size_bytes == limit


class TestDocId:
    def test_identical_bytes_get_identical_ids(self):
        data = pdf_bytes(2)
        # This is what makes a re-upload a cache hit instead of a second paid
        # digitisation call.
        assert store(data).doc_id == store(data, filename="renamed.pdf").doc_id

    def test_different_bytes_get_different_ids(self):
        assert store(pdf_bytes(1)).doc_id != store(pdf_bytes(2)).doc_id

    def test_the_id_is_a_prefixed_sha256_stub(self):
        doc_id = store(png_page(), filename="page.png").doc_id
        assert doc_id.startswith("up_")
        assert len(doc_id) == len("up_") + 16

    def test_the_id_is_a_safe_cache_key(self):
        from askdoc.cache import _check_doc_id

        _check_doc_id(store(png_page(), filename="page.png").doc_id)


class TestStoredFile:
    def test_the_file_is_named_by_content_hash_not_by_the_reader(self, isolated_uploads_dir):
        stored = store(png_page(), filename="../../../etc/passwd.png")
        assert stored.path == isolated_uploads_dir / f"{stored.doc_id}.png"
        assert stored.path.parent == isolated_uploads_dir

    def test_the_original_filename_survives_as_metadata_only(self):
        stored = store(png_page(), filename="../../../etc/passwd.png")
        assert stored.source_filename == "passwd.png"

    def test_a_windows_path_is_reduced_to_its_basename(self):
        stored = store(png_page(), filename=r"C:\Users\me\Desktop\notice.png")
        assert stored.source_filename == "notice.png"

    def test_the_stored_bytes_are_the_uploaded_bytes(self):
        data = pdf_bytes(2)
        assert store(data).path.read_bytes() == data

    def test_size_is_recorded(self):
        data = pdf_bytes(1)
        assert store(data).size_bytes == len(data)

    def test_re_uploading_the_same_file_overwrites_in_place(self, isolated_uploads_dir):
        data = pdf_bytes(1)
        store(data)
        store(data)
        assert len(list(isolated_uploads_dir.iterdir())) == 1

    def test_the_record_is_frozen(self):
        stored = store(png_page(), filename="page.png")
        with pytest.raises(Exception):
            stored.doc_id = "up_0000000000000000"


class TestRejectionCopy:
    def test_the_message_is_the_exception_text(self):
        # api.py hands `.message` straight to the reader; nothing else should
        # ever need to reformat a rejection.
        error = UploadRejected("That file is empty.")
        assert error.message == str(error) == "That file is empty."
