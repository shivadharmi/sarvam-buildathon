"""Speech in and speech out.

The load-bearing test here is `TestTheDocumentCannotBeMisquotedAloud`. Audio
has no visual distinction between the document's words and the model's, so the
guarantee that holds on screen -- a citation is sliced from our own text -- has
to hold in the audio path too, and it holds for the same reason: the caller
sends offsets, not words.

Everything else is transport. These tests stub httpx; none of them spend money.
"""

import httpx
import pytest
from fastapi.testclient import TestClient

from askdoc import api, cache, upload, voice
from askdoc.config import MAX_SPEAK_CHARS
from askdoc.sarvam_http import AuthError, RateLimitError

TAMIL_LINE = "2. இந்த வினாத்தொகுப்பு, 200 வினாக்களைக் கொண்டுள்ளது."


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(cache, "CACHE_DIR", tmp_path / "cache")
    monkeypatch.setattr(upload, "UPLOADS_DIR", tmp_path / "uploads")
    doc = cache.build_doc(
        doc_id="doc_a",
        language="ta-IN",
        raw_blocks=[
            {
                "reading_order": 1,
                "layout_tag": "paragraph",
                "confidence": 0.9,
                "text": TAMIL_LINE,
                "coordinates": {"x1": 0, "y1": 0, "x2": 10, "y2": 10},
            }
        ],
        source_filename="doc_a_page.png",
    )
    cache.save(doc)
    return TestClient(api.app)


@pytest.fixture
def fake_post(monkeypatch):
    """Capture what we send Sarvam and dictate what comes back."""
    calls: list[dict] = []

    def _install(payload: dict, status: int = 200):
        def _post(url, **kwargs):
            calls.append({"url": url, **kwargs})
            return httpx.Response(
                status_code=status,
                json=payload,
                request=httpx.Request("POST", url),
            )

        monkeypatch.setattr(voice.httpx, "post", _post)
        return calls

    return _install


@pytest.fixture(autouse=True)
def api_key(monkeypatch):
    monkeypatch.setenv("SARVAM_API_KEY", "test-key")


class TestTranscribe:
    def test_a_recording_becomes_text(self, fake_post):
        fake_post({"transcript": "தேர்வு எப்போது?"})
        assert voice.transcribe(b"audio", filename="q.webm", language="ta-IN") == (
            "தேர்வு எப்போது?"
        )

    def test_the_page_language_is_sent_not_guessed(self, fake_post):
        calls = fake_post({"transcript": "x"})
        voice.transcribe(b"audio", filename="q.webm", language="te-IN")
        # We know which document is open, so the recogniser is told rather than
        # left to auto-detect.
        assert calls[0]["data"]["language_code"] == "te-IN"

    def test_it_transcribes_rather_than_translates(self, fake_post):
        # The document is in the reader's language and so is every line the
        # model has to point at. A translated question would arrive in English.
        calls = fake_post({"transcript": "x"})
        voice.transcribe(b"audio", filename="q.webm", language="ta-IN")
        assert calls[0]["data"]["mode"] == "transcribe"

    def test_silence_is_reported_as_silence(self, fake_post):
        fake_post({"transcript": "   "})
        with pytest.raises(voice.VoiceError, match="couldn't make out"):
            voice.transcribe(b"audio", filename="q.webm", language="ta-IN")

    def test_an_empty_recording_is_refused_before_paying(self, fake_post):
        calls = fake_post({"transcript": "x"})
        with pytest.raises(voice.VoiceError):
            voice.transcribe(b"", filename="q.webm", language="ta-IN")
        assert calls == []

    def test_an_oversized_recording_is_refused_before_paying(self, fake_post):
        calls = fake_post({"transcript": "x"})
        with pytest.raises(voice.VoiceError, match="too long"):
            voice.transcribe(
                b"x" * (voice.MAX_AUDIO_BYTES + 1), filename="q.webm", language="ta-IN"
            )
        assert calls == []

    def test_a_bad_key_is_an_auth_error(self, fake_post):
        fake_post({}, status=403)
        with pytest.raises(AuthError):
            voice.transcribe(b"audio", filename="q.webm", language="ta-IN")

    def test_a_rate_limit_is_a_rate_limit(self, fake_post):
        fake_post({}, status=429)
        with pytest.raises(RateLimitError):
            voice.transcribe(b"audio", filename="q.webm", language="ta-IN")


class TestSynthesise:
    def test_text_becomes_audio_clips(self, fake_post):
        fake_post({"audios": ["b64one"]})
        assert voice.synthesise("வணக்கம்", language="ta-IN") == (["b64one"], False)

    def test_the_narration_voice_is_used(self, fake_post):
        calls = fake_post({"audios": ["a"]})
        voice.synthesise("x", language="ta-IN")
        # An official page read in a product/IVR voice would lend it a tone it
        # does not have.
        assert calls[0]["json"]["speaker"] == "shreya"

    def test_long_text_is_split_into_several_clips(self, fake_post):
        calls = fake_post({"audios": ["a", "b"]})
        voice.synthesise("word " * 400, language="ta-IN")
        assert len(calls[0]["json"]["inputs"]) > 1

    def test_chunks_break_on_word_boundaries(self):
        pieces = voice._chunks("alpha beta gamma delta " * 60, size=50)
        assert all(len(p) <= 50 for p in pieces)
        # A clip that ends mid-word is audibly wrong.
        assert not any(p.endswith("del") or p.startswith("ta ") for p in pieces)

    def test_reassembling_the_chunks_loses_nothing(self):
        text = "alpha beta gamma delta epsilon " * 30
        assert " ".join(voice._chunks(text, size=40)).split() == text.split()

    def test_empty_text_is_refused(self, fake_post):
        calls = fake_post({"audios": ["a"]})
        with pytest.raises(voice.VoiceError):
            voice.synthesise("   ", language="ta-IN")
        assert calls == []

    def test_no_audio_returned_is_an_error_not_silence(self, fake_post):
        fake_post({"audios": []})
        with pytest.raises(voice.VoiceError, match="no audio"):
            voice.synthesise("x", language="ta-IN")


class TestTheDocumentCannotBeMisquotedAloud:
    """The core invariant, in the audio path.

    On screen a citation is sliced out of our own text. Audio must not be a
    second route by which model- or client-authored words are presented as the
    document's. So the quote path takes *offsets*, and the server does the
    slicing -- the caller never gets to say what the page said.
    """

    def test_a_quote_is_re_sliced_from_our_own_text(self, client, fake_post):
        calls = fake_post({"audios": ["a"]})
        response = client.post(
            "/speak",
            json={
                "doc_id": "doc_a",
                "source": "quote",
                "quote_start": 0,
                "quote_end": len(TAMIL_LINE),
                # A caller trying to put words in the page's mouth. Ignored:
                # the quote path does not read `text` at all.
                "text": "the fee is one rupee",
            },
        )
        assert response.status_code == 200
        spoken = " ".join(calls[0]["json"]["inputs"])
        assert TAMIL_LINE in spoken
        assert "one rupee" not in spoken

    def test_offsets_outside_the_document_are_refused(self, client, fake_post):
        fake_post({"audios": ["a"]})
        response = client.post(
            "/speak",
            json={
                "doc_id": "doc_a",
                "source": "quote",
                "quote_start": 0,
                "quote_end": 99_999,
            },
        )
        assert response.status_code == 400
        assert "doesn't line up" in response.json()["detail"]

    def test_an_inverted_range_is_refused(self, client, fake_post):
        fake_post({"audios": ["a"]})
        response = client.post(
            "/speak",
            json={"doc_id": "doc_a", "source": "quote", "quote_start": 9, "quote_end": 2},
        )
        assert response.status_code == 400

    def test_a_missing_range_is_refused(self, client, fake_post):
        fake_post({"audios": ["a"]})
        response = client.post("/speak", json={"doc_id": "doc_a", "source": "quote"})
        assert response.status_code == 400


class TestSpeakEndpoint:
    def test_an_answer_is_read_from_the_text_it_is_given(self, client, fake_post):
        # Safe for the opposite reason to a quote: an answer was always
        # model-authored prose and is never shown as the page's own words.
        calls = fake_post({"audios": ["a"]})
        response = client.post(
            "/speak",
            json={"doc_id": "doc_a", "source": "answer", "text": "200 questions"},
        )
        assert response.status_code == 200
        assert "200 questions" in " ".join(calls[0]["json"]["inputs"])

    def test_the_documents_language_is_used(self, client, fake_post):
        calls = fake_post({"audios": ["a"]})
        client.post("/speak", json={"doc_id": "doc_a", "source": "answer", "text": "x"})
        assert calls[0]["json"]["target_language_code"] == "ta-IN"
        assert client.post(
            "/speak", json={"doc_id": "doc_a", "source": "answer", "text": "x"}
        ).json()["language"] == "ta-IN"

    def test_an_unknown_document_is_a_404(self, client, fake_post):
        fake_post({"audios": ["a"]})
        response = client.post(
            "/speak", json={"doc_id": "nope", "source": "answer", "text": "x"}
        )
        assert response.status_code == 404

    def test_a_dead_service_is_an_error_not_a_refusal(self, client, fake_post):
        fake_post({}, status=500)
        response = client.post(
            "/speak", json={"doc_id": "doc_a", "source": "answer", "text": "x"}
        )
        assert response.status_code == 502
        assert "not stated" not in response.text


class TestTranscribeEndpoint:
    def test_a_recording_comes_back_as_text(self, client, fake_post):
        fake_post({"transcript": "தேர்வு எப்போது?"})
        response = client.post(
            "/transcribe",
            files={"file": ("q.webm", b"audio", "audio/webm")},
            data={"doc_id": "doc_a"},
        )
        assert response.status_code == 200
        assert response.json() == {"transcript": "தேர்வு எப்போது?"}

    def test_nothing_is_answered_only_transcribed(self, client, fake_post):
        """A transcript is input. Asking it is the reader's decision.

        If this endpoint ever returned an AnswerRecord, a misheard question
        would produce a fully verified citation for something never asked.
        """
        fake_post({"transcript": "தேர்வு எப்போது?"})
        body = client.post(
            "/transcribe",
            files={"file": ("q.webm", b"audio", "audio/webm")},
            data={"doc_id": "doc_a"},
        ).json()
        assert set(body) == {"transcript"}

    def test_an_unknown_document_is_a_404(self, client, fake_post):
        fake_post({"transcript": "x"})
        response = client.post(
            "/transcribe",
            files={"file": ("q.webm", b"audio", "audio/webm")},
            data={"doc_id": "nope"},
        )
        assert response.status_code == 404

    def test_unintelligible_audio_is_a_502_with_a_readable_reason(self, client, fake_post):
        fake_post({"transcript": ""})
        response = client.post(
            "/transcribe",
            files={"file": ("q.webm", b"audio", "audio/webm")},
            data={"doc_id": "doc_a"},
        )
        assert response.status_code == 502
        assert "couldn't make out" in response.json()["detail"]


class TestTruncationIsReportedNotHidden:
    """Audio that just stops looks exactly like a page that just ends.

    Removing the span cap made this reachable: a whole-page citation on doc_a
    is 4478 characters, and the old 4000 ceiling cut it mid-word with nothing
    said. Letting a reader believe they heard the whole citation when they did
    not is the same dishonesty as reporting our own limit as the page's
    silence.
    """

    def test_a_full_page_citation_is_not_truncated(self, fake_post):
        fake_post({"audios": ["a"]})
        _, truncated = voice.synthesise("அ" * 5000, language="ta-IN")
        assert not truncated

    def test_text_past_the_ceiling_reports_truncation(self, fake_post):
        fake_post({"audios": ["a"]})
        _, truncated = voice.synthesise("அ" * (MAX_SPEAK_CHARS + 1), language="ta-IN")
        assert truncated

    def test_the_endpoint_surfaces_it(self, client, fake_post):
        fake_post({"audios": ["a"]})
        body = client.post(
            "/speak",
            json={"doc_id": "doc_a", "source": "answer", "text": "x"},
        ).json()
        assert body["truncated"] is False


class TestOversizedAudioIsRefusedBeforeItIsRead:
    def test_a_huge_recording_is_a_400(self, client, fake_post):
        calls = fake_post({"transcript": "x"})
        response = client.post(
            "/transcribe",
            files={"file": ("q.webm", b"x" * (voice.MAX_AUDIO_BYTES + 1), "audio/webm")},
            data={"doc_id": "doc_a"},
        )
        assert response.status_code == 400
        assert calls == []
