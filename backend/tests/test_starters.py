"""Suggested opening questions.

Two things are being pinned here, and the second is the important one.

First, that starters degrade quietly: every way the model can fail must end in
an empty tuple, because a page whose suggestions failed is still a page you can
ask questions about.

Second, that a suggestion earns no trust by being ours. It is model-authored
input, indistinguishable from something the reader typed, and the answer to one
is verified exactly the same way.

No test here touches the network.
"""

import json

import pytest

from askdoc import cache, pipeline, starters
from askdoc.models import AnswerStatus, ModelAnswer, StarterQuestion
from askdoc.sarvam_http import AuthError, ChatError
from askdoc.structured import MalformedOutput

SOURCE_LINES = [
    "వినతి పత్రము",
    "అంగన్‌వాడీ కార్యకర్త ఖాళీల భర్తీకి దరఖాస్తులు కోరనైనది.",
    "",
    "దరఖాస్తు చేసుకోవడానికి చివరి తేదీ: 15-08-2026",
    "అభ్యర్థి వయస్సు 21 నుండి 35 సంవత్సరాల మధ్య ఉండాలి.",
]

# Deliberately absent from SOURCE_LINES: a starter is written by the model, so
# nothing in it should ever be findable in the document.
MODEL_WRITTEN = [
    {"text": "దరఖాస్తుకు చివరి తేదీ ఏది?", "gloss": "What is the last date to apply?"},
    {"text": "వయస్సు పరిమితి ఎంత?", "gloss": "What is the age limit?"},
    {"text": "ఏ పోస్టుకు దరఖాస్తులు కోరారు?", "gloss": "Which post is being recruited for?"},
]


@pytest.fixture
def doc(tmp_path, monkeypatch):
    monkeypatch.setattr(cache, "CACHE_DIR", tmp_path)
    return cache.build_doc(
        doc_id="doc_b",
        language="te-IN",
        raw_blocks=[
            {
                "reading_order": 1,
                "layout_tag": "paragraph",
                "confidence": 0.95,
                "text": "\n".join(SOURCE_LINES),
                "coordinates": {"x1": 0, "y1": 0, "x2": 100, "y2": 100},
            }
        ],
        source_filename="doc_b_page.png",
    )


@pytest.fixture
def empty_doc(tmp_path, monkeypatch):
    monkeypatch.setattr(cache, "CACHE_DIR", tmp_path)
    return cache.build_doc(
        doc_id="blank",
        language="te-IN",
        raw_blocks=[],
        source_filename="blank.png",
    )


@pytest.fixture
def stub_model(monkeypatch):
    """Replace the one structured call, counting how often it is made."""
    calls: list[list[dict]] = []

    def _stub(payload):
        def _call(messages, _schema, **__):
            calls.append(messages)
            if isinstance(payload, Exception):
                raise payload
            return payload

        monkeypatch.setattr(starters, "complete_structured", _call)
        return calls

    return _stub


class TestGeneration:
    def test_a_page_yields_three_or_four_starters(self, doc, stub_model):
        stub_model({"questions": MODEL_WRITTEN})
        result = starters.generate(doc)
        assert 3 <= len(result) <= 4
        assert all(isinstance(q, StarterQuestion) for q in result)

    def test_both_the_question_and_its_gloss_survive(self, doc, stub_model):
        stub_model({"questions": MODEL_WRITTEN})
        first = starters.generate(doc)[0]
        assert first.text == MODEL_WRITTEN[0]["text"]
        assert first.gloss == MODEL_WRITTEN[0]["gloss"]

    def test_the_document_text_is_what_the_model_is_given(self, doc, stub_model):
        calls = stub_model({"questions": MODEL_WRITTEN})
        starters.generate(doc)
        sent = "".join(m["content"] for m in calls[0])
        assert SOURCE_LINES[3] in sent

    def test_an_over_generous_model_is_trimmed(self, doc, stub_model):
        # Suggestions are a nudge, not a menu; a long list buries the input box.
        stub_model({"questions": MODEL_WRITTEN * 4})
        assert len(starters.generate(doc)) == starters.MAX_STARTERS

    def test_blank_suggestions_are_dropped(self, doc, stub_model):
        stub_model({"questions": [*MODEL_WRITTEN, {"text": "  ", "gloss": "nothing"}]})
        assert len(starters.generate(doc)) == len(MODEL_WRITTEN)

    def test_generated_starters_are_written_to_the_cache(self, doc, stub_model):
        stub_model({"questions": MODEL_WRITTEN})
        result = starters.generate(doc)
        assert cache.load_starters(doc.doc_id) == result


class TestGeneratedOnlyOnce:
    def test_a_cached_set_is_returned_without_calling_the_model(self, doc, stub_model):
        calls = stub_model({"questions": MODEL_WRITTEN})
        first = starters.generate(doc)
        second = starters.generate(doc)
        assert second == first
        assert len(calls) == 1

    def test_a_failure_is_not_cached(self, doc, stub_model):
        # A dead API is a reason to try again later, not a verdict that this
        # page has nothing worth asking.
        stub_model(ChatError("network down"))
        assert starters.generate(doc) == ()
        assert cache.load_starters(doc.doc_id) is None


class TestFailureIsAlwaysSilent:
    """Starters must never take chat down with them."""

    @pytest.mark.parametrize(
        "failure",
        [
            MalformedOutput("not JSON"),
            ChatError("cannot reach sarvam"),
            AuthError("403"),
            RuntimeError("something nobody predicted"),
        ],
    )
    def test_every_kind_of_model_failure_yields_no_starters(self, doc, stub_model, failure):
        stub_model(failure)
        assert starters.generate(doc) == ()

    @pytest.mark.parametrize(
        "payload",
        [
            {},                                     # required field silently omitted
            {"questions": "దరఖాస్తు?"},              # right key, wrong type
            {"questions": [{"gloss": "no text"}]},  # entry missing the question
            {"questions": []},                      # nothing suggested
        ],
    )
    def test_a_wrong_shaped_payload_yields_no_starters(self, doc, stub_model, payload):
        # `json_object` mode returns valid JSON that omits required fields, so
        # the shape is checked rather than assumed.
        stub_model(payload)
        assert starters.generate(doc) == ()

    def test_an_empty_document_is_never_sent_to_the_model(self, empty_doc, stub_model):
        calls = stub_model({"questions": MODEL_WRITTEN})
        assert starters.generate(empty_doc) == ()
        assert calls == []

    def test_an_unreadable_cache_file_yields_no_starters(self, doc, stub_model, tmp_path):
        (tmp_path / f"{doc.doc_id}.starters.json").write_text("{ truncated", encoding="utf-8")
        stub_model({"questions": MODEL_WRITTEN})
        assert starters.generate(doc) == ()


class TestAGeneratedQuestionIsNeverACitation:
    """The core invariant, applied to text this module itself authored.

    A suggested question is input. Answering one runs the same line-anchored
    gate as anything the reader types: the citation is sliced out of our copy
    of the document at a verified range, and the starter earns no shortcut by
    having come from us.
    """

    def test_a_starter_is_model_authored_text_absent_from_the_document(self, doc, stub_model):
        stub_model({"questions": MODEL_WRITTEN})
        for question in starters.generate(doc):
            assert question.text not in doc.text

    def test_answering_a_starter_still_cites_the_documents_own_words(
        self, doc, stub_model, monkeypatch
    ):
        stub_model({"questions": MODEL_WRITTEN})
        starter = starters.generate(doc)[0]

        monkeypatch.setattr(
            pipeline,
            "ask_model",
            lambda *_, **__: ModelAnswer(
                answer="15-08-2026",
                found=True,
                quote_from_line=4,
                quote_to_line=4,
                supporting_quote=starter.text,  # the model quoting its own suggestion
            ),
        )
        record = pipeline.ask(doc, starter.text)

        assert record.status is AnswerStatus.CITED
        assert record.quote == SOURCE_LINES[3]
        assert doc.text[record.quote_start : record.quote_end] == record.quote
        assert starter.text not in record.quote
        # It pointed at line 4 and quoted its own question: flagged, never shown.
        assert record.model_quote_matched is False

    def test_a_starter_with_an_unverifiable_range_is_still_refused(
        self, doc, stub_model, monkeypatch
    ):
        stub_model({"questions": MODEL_WRITTEN})
        starter = starters.generate(doc)[0]

        monkeypatch.setattr(
            pipeline,
            "ask_model",
            lambda *_, **__: ModelAnswer(
                answer="15-08-2026",
                found=True,
                quote_from_line=900,
                quote_to_line=900,
                supporting_quote=starter.text,
            ),
        )
        record = pipeline.ask(doc, starter.text)

        assert record.status is AnswerStatus.NOT_STATED
        assert record.quote is None


class TestThePromptForbidsTranslation:
    """Models render these pages into English unless told not to, repeatedly.

    A starter in English is useless to the reader it is for, so the rule lives
    on the schema property as well as in the prompt.
    """

    def test_the_question_property_demands_the_original_script(self):
        item = starters.STARTERS_SCHEMA["schema"]["properties"]["questions"]["items"]
        assert "never translate" in item["properties"]["text"]["description"].lower()

    def test_the_gloss_is_the_only_place_english_belongs(self):
        assert "english" in json.dumps(starters.STARTERS_SCHEMA).lower()
        assert "never translate" in starters.STARTERS_PROMPT.lower()
