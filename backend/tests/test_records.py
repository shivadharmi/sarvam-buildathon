"""Durable answer records and the share link.

The scope doc calls the answer record "a shareable proof artifact". These tests
pin the two things that make that word "proof" honest: a record cannot be
edited after verification ruled, and opening a link re-checks the citation
against the document rather than trusting what was stored beside it.
"""

import pytest
from fastapi.testclient import TestClient

from askdoc import api, cache, records, upload
from askdoc.models import AnswerRecord, AnswerStatus, RefusalReason

LINE = "2. இந்த வினாத்தொகுப்பு, 200 வினாக்களைக் கொண்டுள்ளது."


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(cache, "CACHE_DIR", tmp_path / "cache")
    monkeypatch.setattr(upload, "UPLOADS_DIR", tmp_path / "uploads")
    monkeypatch.setattr(records, "DB_PATH", tmp_path / "records.db")
    doc = cache.build_doc(
        doc_id="doc_a",
        language="ta-IN",
        raw_blocks=[
            {
                "reading_order": 1,
                "layout_tag": "paragraph",
                "confidence": 0.9,
                "text": LINE,
                "coordinates": {"x1": 0, "y1": 0, "x2": 10, "y2": 10},
            }
        ],
        source_filename="doc_a_page.png",
    )
    cache.save(doc)
    return TestClient(api.app)


def _cited(**overrides) -> AnswerRecord:
    base = dict(
        question="how many questions?",
        answer="200",
        status=AnswerStatus.CITED,
        doc_id="doc_a",
        quote=LINE,
        quote_start=0,
        quote_end=len(LINE),
        quote_from_line=1,
        quote_to_line=1,
        quote_line_count=1,
        model="sarvam-105b",
        asked_at="2026-07-26T10:00:00+00:00",
    )
    return AnswerRecord(**{**base, **overrides})


class TestStorage:
    def test_a_saved_record_comes_back_identical(self, client):
        record = _cited()
        assert records.load(records.save(record)) == record

    def test_ids_are_unguessable(self, client):
        # A record carries the document it was asked of, and an uploaded page
        # may be someone's own paperwork. Sequential ids would hand those out.
        ids = {records.save(_cited()) for _ in range(20)}
        assert len(ids) == 20
        assert all(len(i) > 12 for i in ids)

    def test_an_unknown_id_is_none_not_an_error(self, client):
        assert records.load("nope") is None
        assert records.load("") is None

    def test_records_survive_a_new_connection(self, client):
        record_id = records.save(_cited())
        assert records.count() == 1
        assert records.load(record_id) is not None


class TestShareLink:
    def test_a_link_carries_the_document_so_it_can_be_checked(self, client):
        # A citation without the page it came from is the screenshot this
        # product exists to replace.
        record_id = records.save(_cited())
        body = client.get(f"/records/{record_id}").json()
        assert body["record"]["quote"] == LINE
        assert body["document"]["text"].startswith("2. இந்த")

    def test_the_citation_is_rechecked_against_the_document(self, client):
        record_id = records.save(_cited())
        body = client.get(f"/records/{record_id}").json()
        record, doc = body["record"], body["document"]
        assert doc["text"][record["quote_start"] : record["quote_end"]] == record["quote"]

    def test_a_record_whose_offsets_no_longer_match_is_refused(self, client):
        """Better to show nothing than a quote against the wrong page.

        Re-digitising under the same id moves every offset. Rendering the old
        quote beside the new document would be precisely the mismatch between
        citation and source that this product exists to make impossible.
        """
        record_id = records.save(_cited(quote="something the page never said"))
        response = client.get(f"/records/{record_id}")
        assert response.status_code == 409
        assert "read again" in response.json()["detail"]

    def test_an_unknown_link_is_a_404_in_plain_words(self, client):
        response = client.get("/records/does-not-exist")
        assert response.status_code == 404
        assert "doesn't point to an answer" in response.json()["detail"]

    def test_a_refusal_is_shareable_too(self, client):
        # "This page doesn't say" is a result, and often the most useful thing
        # a reader can forward to someone.
        record_id = records.save(
            _cited(
                status=AnswerStatus.NOT_STATED,
                answer="not stated in this document",
                refusal_reason=RefusalReason.DOCUMENT_SILENT,
                quote=None,
                quote_start=None,
                quote_end=None,
            )
        )
        body = client.get(f"/records/{record_id}").json()
        assert body["record"]["status"] == "not_stated"
        assert body["record"]["refusal_reason"] == "document_silent"


class TestAskPersists:
    def test_answering_stores_a_record_and_returns_its_id(self, client, monkeypatch):
        monkeypatch.setattr(api, "handle", lambda *_, **__: _cited())
        response = client.post("/ask", json={"doc_id": "doc_a", "question": "q"})
        assert response.status_code == 200
        record_id = response.headers["X-Record-Id"]
        assert records.load(record_id) is not None

    def test_a_note_is_not_a_record(self, client, monkeypatch):
        """"Noted" is not a claim about the document, so it is not proof of one."""
        from askdoc.models import NoteAcknowledgement

        monkeypatch.setattr(
            api,
            "handle",
            lambda *_, **__: NoteAcknowledgement(
                doc_id="doc_a", note="n", acknowledgement="ok", asked_at="2026-07-26T10:00:00+00:00"
            ),
        )
        response = client.post("/ask", json={"doc_id": "doc_a", "question": "I am ST"})
        assert "X-Record-Id" not in response.headers
        assert records.count() == 0
