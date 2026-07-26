"""The cache is the offline demo fallback, so round-tripping must be exact."""

import unicodedata

import pytest

from askdoc import cache
from askdoc.gate import check_quote


@pytest.fixture(autouse=True)
def isolated_cache_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(cache, "CACHE_DIR", tmp_path)
    return tmp_path


def block(text, order=1, tag="paragraph"):
    return {
        "reading_order": order,
        "layout_tag": tag,
        "confidence": 0.9,
        "text": text,
        "coordinates": {"x1": 10.0, "y1": 20.0, "x2": 300.0, "y2": 40.0},
    }


def make_doc(doc_id="doc_a", blocks=None):
    return cache.build_doc(
        doc_id=doc_id,
        language="ta-IN",
        raw_blocks=blocks or [block("மொத்த காலிப் பணியிடங்கள்: 1234")],
        source_filename="doc_a_page.png",
    )


class TestBuildDoc:
    def test_text_is_nfc_normalised(self):
        decomposed = unicodedata.normalize("NFD", "மொத்த காலிப் பணியிடங்கள்")
        doc = make_doc(blocks=[block(decomposed)])
        assert doc.text == unicodedata.normalize("NFC", decomposed)

    def test_blocks_are_ordered_by_reading_order(self):
        doc = make_doc(blocks=[block("second", order=2), block("first", order=1)])
        assert doc.text == "first\n\nsecond"

    def test_block_offsets_slice_the_assembled_text(self):
        doc = make_doc(blocks=[block("first", order=1), block("second", order=2)])
        for b in doc.blocks:
            assert doc.text[b.start : b.end] == b.text

    def test_quote_offset_resolves_back_to_its_block(self):
        # This is what would let a highlight be drawn on the page image.
        doc = make_doc(blocks=[block("header", order=1), block("கட்டணம் ரூ.150", order=2)])
        verdict = check_quote("ரூ.150", doc.text)
        assert doc.block_at(verdict.start).layout_tag == "paragraph"

    def test_coordinates_are_retained(self):
        assert make_doc().blocks[0].x2 == 300.0

    def test_empty_blocks_are_dropped(self):
        doc = make_doc(blocks=[block("real", order=1), block("   ", order=2)])
        assert len(doc.blocks) == 1

    def test_quote_offsets_index_into_the_stored_text(self):
        # The contract that makes highlighting work: the gate's offsets must
        # slice the exact string we cached and will render.
        doc = make_doc()
        result = check_quote("காலிப் பணியிடங்கள்", doc.text)
        assert result.passed
        assert doc.text[result.start : result.end] == "காலிப் பணியிடங்கள்"

    def test_records_when_it_was_digitised(self):
        assert make_doc().digitised_at


class TestRoundTrip:
    def test_saved_document_loads_back_identically(self):
        doc = make_doc()
        cache.save(doc)
        assert cache.load("doc_a") == doc

    def test_tamil_text_survives_the_json_round_trip(self):
        doc = make_doc()
        cache.save(doc)
        assert cache.load("doc_a").text == doc.text

    def test_missing_document_returns_none(self):
        assert cache.load("never_digitised") is None

    def test_list_cached_is_ordered_by_digitisation_time(self):
        cache.save(make_doc(doc_id="doc_a"))
        cache.save(make_doc(doc_id="doc_b"))
        assert [d.doc_id for d in cache.list_cached()] == ["doc_a", "doc_b"]

    def test_list_cached_is_empty_before_anything_is_digitised(self):
        assert cache.list_cached() == []


class TestPathSafety:
    @pytest.mark.parametrize("doc_id", ["", "../escape", "a/b", ".hidden"])
    def test_unsafe_doc_ids_are_rejected(self, doc_id):
        with pytest.raises(ValueError):
            cache.load(doc_id)
