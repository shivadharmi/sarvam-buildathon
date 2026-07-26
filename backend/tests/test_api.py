"""HTTP surface.

The behaviour worth pinning here is the error mapping. "We could not reach the
model" and "the document does not say" are completely different claims, and
collapsing the first into the second would be exactly the dishonesty this
product exists to prevent.

The upload endpoints add a second theme: what a paid call costs. Re-uploading
the same page, or confirming the language it was already read in, must not
touch the digitiser at all, and the tests below count the calls rather than
taking that on trust.

Every `detail` string here is shown to the reader verbatim by the frontend, so
these tests also read as a check on the copy.
"""

import pytest
from fastapi.testclient import TestClient

from askdoc import api, cache, jobs, starters, upload
from askdoc.jobs import Registry
from askdoc.models import AnswerRecord, AnswerStatus, LanguageSource
from askdoc.sarvam_http import AuthError, ChatError, RateLimitError

from .test_jobs import DEVANAGARI, FakeDigitiser, resolution

# A real 1x1 PNG, padded past the plausibility floor in upload.py. Nothing here
# decodes the padding.
PNG_PAGE = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01"
    b"\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
) + b"\x00" * 2048


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(cache, "CACHE_DIR", tmp_path / "cache")
    monkeypatch.setattr(upload, "UPLOADS_DIR", tmp_path / "uploads")
    monkeypatch.setattr(jobs, "REGISTRY", Registry())
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


@pytest.fixture
def digitiser(monkeypatch):
    """A stand-in for the paid call, wired into the ingestion runner."""
    fake = FakeDigitiser()
    monkeypatch.setattr(jobs, "digitise", fake)
    monkeypatch.setattr(jobs, "resolve_language", lambda *_, **__: resolution())
    return fake


def upload_page(client, content: bytes = PNG_PAGE, filename: str = "scan.png"):
    return client.post("/documents", files={"file": (filename, content, "image/png")})


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

    def test_the_list_carries_the_full_text(self, client):
        # The UI renders the page straight off this list rather than fetching
        # each document again.
        assert "வினாத்தொகுப்பு" in client.get("/documents").json()[0]["text"]

    def test_fetches_one_document(self, client):
        assert client.get("/documents/doc_a").json()["language"] == "ta-IN"

    def test_a_missing_document_is_explained_to_the_reader_not_the_operator(self, client):
        # This string is shown verbatim in the UI, so it must not be a CLI
        # instruction -- the reader who hits it has no shell.
        response = client.get("/documents/doc_b")
        assert response.status_code == 404
        assert response.json()["detail"] == api.NO_SUCH_DOCUMENT

    def test_unknown_document_is_not_found(self, client):
        assert client.get("/documents/nope").status_code == 404

    @pytest.mark.parametrize("doc_id", ["doc_a.starters", "Doc_A", "doc a", "doc_a."])
    def test_an_unsafe_id_is_simply_not_found(self, client, doc_id):
        # cache._path_for whitelists the shape of an id, so one that cannot
        # name a file is refused before the filesystem is touched -- and is
        # answered with the ordinary "no such document", not a hint that the
        # shape was the problem.
        response = client.get(f"/documents/{doc_id}")
        assert response.status_code == 404
        assert response.json()["detail"] == api.NO_SUCH_DOCUMENT

    @pytest.mark.parametrize("doc_id", ["../../etc/passwd", "..%2F..%2Fcache%2Fdoc_a"])
    def test_a_traversal_attempt_never_reaches_a_handler(self, client, doc_id):
        assert client.get(f"/documents/{doc_id}").status_code == 404

    def test_a_corrupt_document_is_loud_rather_than_missing(self, client):
        # Deliberately not skipped. A document that vanishes from the library
        # without a word teaches the reader it was never uploaded -- and the
        # two demo documents are the offline fallback, so losing one quietly is
        # the failure most worth making loud.
        (cache.CACHE_DIR / "doc_a.json").write_text("{not json", encoding="utf-8")

        with pytest.raises(Exception):
            client.get("/documents")

    def test_health_reports_available_documents(self, client):
        health = client.get("/health").json()
        assert health["ok"] is True
        assert health["documents"] == ["doc_a"]
        # Records are counted too, so a restart that lost the store is visible.
        assert isinstance(health["records"], int)


class TestUpload:
    def test_an_accepted_page_returns_only_a_job_id(self, client, digitiser):
        response = upload_page(client)
        assert response.status_code == 202
        # Nothing else: a 202 must not look like a finished upload.
        assert set(response.json()) == {"job_id"}

    def test_the_page_is_read_and_published(self, client, digitiser):
        job_id = upload_page(client).json()["job_id"]
        job = client.get(f"/jobs/{job_id}").json()

        assert job["state"] == "ready"
        assert digitiser.languages == ["hi-IN", "ta-IN"]
        assert client.get(f"/documents/{job['doc_id']}").json()["language"] == "ta-IN"

    def test_the_upload_is_labelled_with_the_readers_own_filename(self, client, digitiser):
        job_id = upload_page(client, filename="circular.png").json()["job_id"]
        doc_id = client.get(f"/jobs/{job_id}").json()["doc_id"]

        assert client.get(f"/documents/{doc_id}").json()["label"] == "circular.png"

    def test_the_same_bytes_are_the_same_document_and_cost_nothing(self, client, digitiser):
        doc_id = client.get(
            f"/jobs/{upload_page(client).json()['job_id']}"
        ).json()["doc_id"]
        digitiser.languages.clear()

        body = upload_page(client, filename="a-different-name.png")

        assert body.status_code == 200
        assert body.json()["doc_id"] == doc_id
        assert body.json()["state"] == "ready"
        # The point of content-hash identity: no second paid call, ever.
        assert digitiser.languages == []

    def test_a_rejected_file_is_refused_in_the_readers_words(self, client, digitiser):
        response = client.post(
            "/documents", files={"file": ("notes.txt", b"plain text" * 500, "text/plain")}
        )

        assert response.status_code == 400
        assert response.json()["detail"] == upload.UNSUPPORTED_TYPE
        assert digitiser.languages == []

    def test_the_declared_size_is_passed_on(self, client, digitiser, monkeypatch):
        # store_upload can refuse an oversized file before reading a byte, but
        # only when it is told how big the file claims to be. Without this the
        # reader still gets refused, just later and in vaguer words.
        seen = {}
        real = api.store_upload

        def spy(stream, **kwargs):
            seen.update(kwargs)
            return real(stream, **kwargs)

        monkeypatch.setattr(api, "store_upload", spy)
        upload_page(client)

        assert seen["declared_bytes"] == len(PNG_PAGE)

    def test_a_file_that_is_too_small_says_so_rather_than_being_read(self, client, digitiser):
        response = client.post("/documents", files={"file": ("tiny.png", b"\x89PNG\r\n\x1a\n")})

        assert response.status_code == 400
        assert response.json()["detail"] == upload.TOO_SMALL


class TestJobStatus:
    def test_an_unknown_job_is_not_found(self, client):
        assert client.get("/jobs/job_nope").status_code == 404

    def test_a_failure_reports_a_reason_the_reader_can_act_on(self, client, monkeypatch):
        def boom(*_, **__):
            raise jobs.DigitisationError("PartiallyCompleted")

        monkeypatch.setattr(jobs, "digitise", boom)
        job_id = upload_page(client).json()["job_id"]
        job = client.get(f"/jobs/{job_id}").json()

        assert job["state"] == "failed"
        assert job["error"] == jobs.COULD_NOT_READ
        # Not a document with no text: a page we could not read is not a page
        # that says nothing.
        assert client.get(f"/documents/{job['doc_id']}").status_code == 404

    def test_the_probe_text_is_never_serialised(self, client, needs_language_job):
        # It is a paid call held in hand, not part of the job's public shape.
        assert "probe" not in needs_language_job


@pytest.fixture
def needs_language_job(client, monkeypatch):
    monkeypatch.setattr(jobs, "digitise", FakeDigitiser(DEVANAGARI))
    monkeypatch.setattr(
        jobs,
        "resolve_language",
        lambda *_, **__: resolution(
            language=None,
            source=LanguageSource.USER,
            script="Deva",
            lid_language="hi-IN",
            needs_user=True,
        ),
    )
    job_id = upload_page(client).json()["job_id"]
    return client.get(f"/jobs/{job_id}").json()


class TestNeedsLanguageIsAnswerable:
    def test_it_is_terminal_and_carries_no_error(self, needs_language_job):
        assert needs_language_job["state"] == "needs_language"
        assert needs_language_job["stage"] == "needs_language"
        assert needs_language_job["error"] is None

    def test_it_names_the_document_the_picker_has_to_post_to(self, needs_language_job):
        # Without doc_id this state is unanswerable and the reader is stuck.
        assert needs_language_job["doc_id"].startswith("up_")

    def test_it_offers_what_lid_thought_without_having_acted_on_it(self, needs_language_job):
        assert needs_language_job["script"] == "Deva"
        assert needs_language_job["detected_language"] == "hi-IN"


class TestLanguageOverride:
    def test_it_re_reads_the_stored_original(self, client, digitiser):
        doc_id = client.get(
            f"/jobs/{upload_page(client).json()['job_id']}"
        ).json()["doc_id"]
        digitiser.languages.clear()

        response = client.post(f"/documents/{doc_id}/language", json={"language": "mr-IN"})

        assert response.status_code == 202
        assert set(response.json()) == {"job_id"}
        assert digitiser.languages == ["mr-IN"]

        doc = client.get(f"/documents/{doc_id}").json()
        assert doc["language"] == "mr-IN"
        assert doc["language_source"] == "user"

    def test_answering_the_picker_reuses_the_probe_it_already_paid_for(
        self, client, needs_language_job, monkeypatch
    ):
        fake = FakeDigitiser(DEVANAGARI)
        monkeypatch.setattr(jobs, "digitise", fake)
        doc_id = needs_language_job["doc_id"]

        response = client.post(f"/documents/{doc_id}/language", json={"language": "hi-IN"})

        assert response.status_code == 202
        assert fake.languages == []
        assert client.get(f"/documents/{doc_id}").json()["language_source"] == "user"

    def test_confirming_the_language_already_read_is_a_no_op(self, client, digitiser):
        response = client.post("/documents/doc_a/language", json={"language": "ta-IN"})

        assert response.status_code == 200
        assert response.json()["doc_id"] == "doc_a"
        assert response.json()["state"] == "ready"
        assert digitiser.languages == []

    def test_a_language_we_cannot_digitise_is_refused(self, client, digitiser):
        response = client.post("/documents/doc_a/language", json={"language": "fr-FR"})

        assert response.status_code == 400
        assert "fr-FR" in response.json()["detail"]
        assert digitiser.languages == []

    def test_a_document_whose_original_is_gone_says_so(self, client, digitiser):
        # doc_a is builtin: there are no uploaded bytes to re-read.
        response = client.post("/documents/doc_a/language", json={"language": "te-IN"})

        assert response.status_code == 404
        assert response.json()["detail"] == api.ORIGINAL_GONE

    def test_an_unsafe_document_id_is_not_found(self, client, digitiser):
        response = client.post("/documents/doc_a.starters/language", json={"language": "ta-IN"})

        assert response.status_code == 404
        assert response.json()["detail"] == api.NO_SUCH_DOCUMENT
        assert digitiser.languages == []


class TestStarters:
    def test_generated_questions_are_returned(self, client, monkeypatch):
        monkeypatch.setattr(
            starters,
            "complete_structured",
            lambda *_, **__: {
                "questions": [
                    {"text": "எத்தனை வினாக்கள்?", "gloss": "How many questions?"},
                ]
            },
        )
        body = client.get("/documents/doc_a/starters").json()
        assert body == [{"text": "எத்தனை வினாக்கள்?", "gloss": "How many questions?"}]

    def test_a_failure_is_an_empty_list_not_an_error(self, client, monkeypatch):
        def boom(*_, **__):
            raise ChatError("no")

        monkeypatch.setattr(starters, "complete_structured", boom)
        response = client.get("/documents/doc_a/starters")

        # A page whose suggestions failed is still a page you can ask about.
        assert response.status_code == 200
        assert response.json() == []

    def test_generating_starters_does_not_break_the_document_list(self, client, monkeypatch):
        monkeypatch.setattr(
            starters,
            "complete_structured",
            lambda *_, **__: {"questions": [{"text": "எத்தனை?", "gloss": "How many?"}]},
        )
        client.get("/documents/doc_a/starters")

        assert client.get("/documents").status_code == 200


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
