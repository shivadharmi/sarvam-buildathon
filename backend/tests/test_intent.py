"""One input box: is this message a question, or something the reader told us?

The safety property under test is the bias. Misreading a question as a
statement swallows it silently -- the reader is told "noted" and never learns
the page could have answered. Misreading a statement as a question yields a
visible refusal they can recover from. So every uncertain path must resolve to
"question".
"""

import pytest

from askdoc import intent, pipeline
from askdoc.intent import classify, looks_like_a_question
from askdoc.models import AnswerStatus, ModelAnswer, NoteAcknowledgement
from askdoc.sarvam_http import ChatError
from askdoc import cache


class TestQuestionMarkFastPath:
    """Skips a model call on the overwhelmingly common case."""

    @pytest.mark.parametrize(
        "message",
        [
            "எத்தனை வினாக்கள் உள்ளன?",
            "దరఖాస్తు రుసుము ఎంత?",
            "how many questions?",
            "  trailing space?  ",
        ],
    )
    def test_a_trailing_question_mark_is_enough(self, message):
        assert looks_like_a_question(message)

    def test_a_statement_is_not_matched(self):
        assert not looks_like_a_question("నేను మల్దకల్ ప్రాజెక్టుకు దరఖాస్తు చేస్తున్నాను.")

    def test_the_fast_path_makes_no_model_call(self, monkeypatch):
        def explode(*_, **__):
            raise AssertionError("should not have called the model")

        monkeypatch.setattr(intent, "complete_structured", explode)
        assert classify("எத்தனை வினாக்கள் உள்ளன?") == (True, "")


class TestClassification:
    def test_a_statement_is_recognised(self, monkeypatch):
        monkeypatch.setattr(
            intent,
            "complete_structured",
            lambda *_, **__: {
                "reason": "states which project",
                "is_a_question": False,
                "acknowledgement": "మల్దకల్ ప్రాజెక్టు గుర్తుంచుకున్నాను.",
            },
        )
        is_question, ack = classify("నేను మల్దకల్ ప్రాజెక్టుకు దరఖాస్తు చేస్తున్నాను.")
        assert is_question is False
        assert "మల్దకల్" in ack

    def test_a_question_without_a_question_mark_still_answers(self, monkeypatch):
        monkeypatch.setattr(
            intent,
            "complete_structured",
            lambda *_, **__: {"reason": "asks", "is_a_question": True, "acknowledgement": ""},
        )
        assert classify("tell me the last date")[0] is True


class TestBiasTowardAnswering:
    """Every failure path must resolve to "question"."""

    def test_a_classifier_outage_answers(self, monkeypatch):
        def boom(*_, **__):
            raise ChatError("down")

        monkeypatch.setattr(intent, "complete_structured", boom)
        assert classify("some statement") == (True, "")

    def test_a_malformed_verdict_answers(self, monkeypatch):
        monkeypatch.setattr(intent, "complete_structured", lambda *_, **__: {})
        assert classify("some statement")[0] is True

    def test_a_missing_field_answers(self, monkeypatch):
        monkeypatch.setattr(
            intent, "complete_structured", lambda *_, **__: {"reason": "unsure"}
        )
        assert classify("some statement")[0] is True


class TestPipelineRouting:
    @pytest.fixture
    def doc(self, tmp_path, monkeypatch):
        monkeypatch.setattr(cache, "CACHE_DIR", tmp_path)
        return cache.build_doc(
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

    def test_a_statement_becomes_a_note_and_never_reaches_the_model(self, doc, monkeypatch):
        monkeypatch.setattr(pipeline, "classify", lambda _: (False, "సరే, గుర్తుంచుకున్నాను."))

        def explode(*_, **__):
            raise AssertionError("a statement must not be sent for answering")

        monkeypatch.setattr(pipeline, "ask_model", explode)

        result = pipeline.handle(doc, "నేను మల్దకల్ ప్రాజెక్టుకు దరఖాస్తు చేస్తున్నాను.")
        assert isinstance(result, NoteAcknowledgement)
        assert result.note == "నేను మల్దకల్ ప్రాజెక్టుకు దరఖాస్తు చేస్తున్నాను."
        assert result.acknowledgement == "సరే, గుర్తుంచుకున్నాను."

    def test_a_question_is_answered_normally(self, doc, monkeypatch):
        monkeypatch.setattr(pipeline, "classify", lambda _: (True, ""))
        monkeypatch.setattr(
            pipeline,
            "ask_model",
            lambda *_, **__: ModelAnswer(
                answer="200", found=True, quote_from_line=1, quote_to_line=1
            ),
        )
        result = pipeline.handle(doc, "எத்தனை வினாக்கள்?")
        assert result.status is AnswerStatus.CITED

    def test_an_empty_acknowledgement_still_replies(self, doc, monkeypatch):
        monkeypatch.setattr(pipeline, "classify", lambda _: (False, ""))
        assert pipeline.handle(doc, "a statement").acknowledgement == "Noted."


class TestAcknowledgementsAreReceiptsNotAdvice:
    """A note is acknowledged, never answered with advice.

    Observed live during M5: "I am applying to the Maldakal project" came back
    as "Submit the eligibility documents." The classifier has not read the page
    at that point, so any instruction it gives is invented -- and unfounded
    advice on an official document is exactly what §6 rules out. It also arrives
    dressed as the product's own voice, which is worse than a wrong answer,
    because nothing on screen marks it as a guess.
    """

    def test_the_prompt_forbids_instructions(self):
        assert "Never tell the reader what to do" in intent.CLASSIFY_PROMPT
        assert "is invented" in intent.CLASSIFY_PROMPT

    def test_the_prompt_shows_what_a_receipt_looks_like(self):
        # Asserting the shape positively: a bare prohibition left the model to
        # guess what to write instead.
        assert "receipt, not a reply" in intent.CLASSIFY_PROMPT
        assert "you are applying to the Maldakal project" in intent.CLASSIFY_PROMPT

    def test_the_schema_carries_the_rule_too(self):
        # The prompt alone was not enough for the quote-language rule either.
        described = intent.INTENT_SCHEMA["schema"]["properties"]["acknowledgement"]
        assert "no advice and no instruction" in described["description"]

    def test_the_language_rule_comes_after_the_english_examples(self):
        """Order is load-bearing, and getting it wrong shipped a regression.

        The shape examples are written in English. With the language rule stated
        only *before* them, the model copied their language too: a Tamil note
        came back acknowledged in English. Restating it last fixed all three
        scripts tested.
        """
        prompt = intent.CLASSIFY_PROMPT
        assert prompt.index("SHAPE only") < prompt.index("SAME LANGUAGE")
        assert "Tamil in, Tamil out" in prompt
