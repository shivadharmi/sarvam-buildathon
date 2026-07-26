"""HTTP surface.

The behaviour worth pinning here is the error mapping. "We could not reach the
model" and "the document does not say" are completely different claims, and
collapsing the first into the second would be exactly the dishonesty this
product exists to prevent.
"""

import pytest
from fastapi.testclient import TestClient

from askdoc import api, cache
from askdoc.models import AnswerRecord, AnswerStatus
from askdoc.sarvam_http import AuthError, ChatError, RateLimitError


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(cache, "CACHE_DIR", tmp_path)
    doc = cache.build_doc(
        doc_id="doc_a",
        language="ta-IN",
        raw_blocks=[
            {
                "reading_order": 1,
                "layout_tag": "paragraph",
                "confidence": 0.9,
                "text": "2. இந்த வினாத்தொகுப்பு, 200 வினாக்களைக் கொண்டுள்ளது.",
                "coordinates": {"x1": 0, "y1": 0, "x2": 10, "y2": 10},
            }
        ],
        source_filename="doc_a_page.png",
    )
    cache.save(doc)
    return TestClient(api.app)


def cited_record() -> AnswerRecord:
    return AnswerRecord(
        question="q",
        answer="200",
        status=AnswerStatus.CITED,
        doc_id="doc_a",
        quote="2. இந்த வினாத்தொகுப்பு, 200 வினாக்களைக் கொண்டுள்ளது.",
        quote_start=0,
        quote_end=51,
        quote_from_line=1,
        quote_to_line=1,
        model="sarvam-105b",
        asked_at="2026-07-26T00:00:00+00:00",
    )


class TestDocuments:
    def test_lists_cached_documents(self, client):
        body = client.get("/documents").json()
        assert [d["doc_id"] for d in body] == ["doc_a"]

    def test_fetches_one_document(self, client):
        assert client.get("/documents/doc_a").json()["language"] == "ta-IN"

    def test_undigitised_document_explains_how_to_fix_it(self, client):
        response = client.get("/documents/doc_b")
        assert response.status_code == 404
        assert "digitise" in response.json()["detail"]

    def test_unknown_document_is_not_found(self, client):
        assert client.get("/documents/nope").status_code == 404

    def test_health_reports_available_documents(self, client):
        assert client.get("/health").json() == {"ok": True, "documents": ["doc_a"]}


class TestAsk:
    def test_returns_the_answer_record(self, client, monkeypatch):
        monkeypatch.setattr(api, "handle", lambda *_, **__: cited_record())
        body = client.post("/ask", json={"doc_id": "doc_a", "question": "how many?"}).json()
        assert body["status"] == "cited"
        assert body["quote_from_line"] == 1

    def test_rejects_an_empty_question(self, client):
        response = client.post("/ask", json={"doc_id": "doc_a", "question": ""})
        assert response.status_code == 422

    def test_rejects_an_unknown_document(self, client):
        response = client.post("/ask", json={"doc_id": "nope", "question": "q"})
        assert response.status_code == 404


class TestErrorsAreNotDisguisedAsRefusals:
    @pytest.mark.parametrize(
        "error,status",
        [
            (AuthError("bad key"), 502),
            (RateLimitError("slow down"), 429),
            (ChatError("network down"), 502),
        ],
    )
    def test_model_failures_surface_as_errors(self, client, monkeypatch, error, status):
        def boom(*_, **__):
            raise error

        monkeypatch.setattr(api, "handle", boom)
        response = client.post("/ask", json={"doc_id": "doc_a", "question": "q"})

        assert response.status_code == status
        # Crucially, NOT a 200 carrying "not stated in this document".
        assert "not stated" not in response.text
