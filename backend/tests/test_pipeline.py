"""The decision logic: when does a claim become a citation?

These tests stub the model entirely. That is the point -- the pipeline's job is
to decide what to do with whatever the model says, including when it lies, and
that decision must be testable without a network call.
"""

import pytest

from askdoc import cache, pipeline
from askdoc.models import AnswerStatus, ModelAnswer, RefusalReason

SOURCE_LINES = [
    "வினாத்தொகுப்பு எண்: 22166409",
    "கால அளவு : மூன்று மணி நேரம்",
    "",
    "2. இந்த வினாத்தொகுப்பு, 200 வினாக்களைக் கொண்டுள்ளது.",
    "9. உங்களுக்கு விடை தெரியவில்லை எனில், (E) என்பதை அவசியம் நிரப்ப வேண்டும்.",
]


@pytest.fixture
def doc(tmp_path, monkeypatch):
    monkeypatch.setattr(cache, "CACHE_DIR", tmp_path)
    return cache.build_doc(
        doc_id="doc_a",
        language="ta-IN",
        raw_blocks=[
            {
                "reading_order": 1,
                "layout_tag": "ordered-list",
                "confidence": 0.95,
                "text": "\n".join(SOURCE_LINES),
                "coordinates": {"x1": 0, "y1": 0, "x2": 100, "y2": 100},
            }
        ],
        source_filename="doc_a_page.png",
    )


@pytest.fixture
def long_doc(tmp_path, monkeypatch):
    """A page long enough that the proportional cap bites before the bounds."""
    monkeypatch.setattr(cache, "CACHE_DIR", tmp_path)
    return cache.build_doc(
        doc_id="long",
        language="ta-IN",
        raw_blocks=[
            {
                "reading_order": 1,
                "layout_tag": "paragraph",
                "confidence": 0.9,
                "text": "\n".join(f"line {i} of the notice" for i in range(1, 41)),
                "coordinates": {"x1": 0, "y1": 0, "x2": 10, "y2": 10},
            }
        ],
        source_filename="long.png",
    )


@pytest.fixture
def stub_model(monkeypatch):
    """Replace the model with a fixed claim."""

    def _stub(**claim):
        answer = ModelAnswer(**claim)
        monkeypatch.setattr(pipeline, "ask_model", lambda *_, **__: answer)
        return answer

    return _stub


class TestRefusals:
    def test_model_saying_not_found_is_honoured_immediately(self, doc, stub_model):
        stub_model(answer="not here", found=False)
        assert pipeline.ask(doc, "q").status is AnswerStatus.NOT_STATED

    @pytest.mark.parametrize(
        "from_line,to_line",
        [
            (0, 1),        # zero is not a line
            (1, 999),      # past the end
            (4, 2),        # inverted
            (3, 3),        # blank line
            (1, 99),  # past the end of the document
        ],
    )
    def test_unusable_line_ranges_are_refused(self, doc, stub_model, from_line, to_line):
        stub_model(
            answer="200 questions",
            found=True,
            quote_from_line=from_line,
            quote_to_line=to_line,
            supporting_quote="anything",
        )
        record = pipeline.ask(doc, "q")
        assert record.status is AnswerStatus.NOT_STATED
        assert record.refusal_reason

    def test_refusal_carries_no_citation(self, doc, stub_model):
        stub_model(answer="x", found=True, quote_from_line=99, quote_to_line=99)
        record = pipeline.ask(doc, "q")
        assert record.quote is None
        assert record.quote_start is None

    def test_refused_answer_text_is_replaced_not_softened(self, doc, stub_model):
        # The model's prose must not survive a failed verification.
        stub_model(
            answer="The booklet probably has around 200 questions.",
            found=True,
            quote_from_line=999,
            quote_to_line=999,
        )
        record = pipeline.ask(doc, "q")
        assert "probably" not in record.answer
        assert record.answer == "could not verify a citation for this on the page"

    def test_overruled_flag_marks_a_rejected_claim(self, doc, stub_model):
        stub_model(answer="x", found=True, quote_from_line=99, quote_to_line=99)
        assert pipeline.ask(doc, "q").was_overruled


class TestCitations:
    def test_valid_range_produces_a_citation(self, doc, stub_model):
        stub_model(
            answer="200 questions",
            found=True,
            quote_from_line=4,
            quote_to_line=4,
            supporting_quote=SOURCE_LINES[3],
        )
        record = pipeline.ask(doc, "q")
        assert record.status is AnswerStatus.CITED
        assert record.quote == SOURCE_LINES[3]

    def test_quote_offsets_slice_the_document(self, doc, stub_model):
        stub_model(answer="a", found=True, quote_from_line=4, quote_to_line=5)
        record = pipeline.ask(doc, "q")
        assert doc.text[record.quote_start : record.quote_end] == record.quote

    def test_citation_comes_from_the_document_not_the_model(self, doc, stub_model):
        """The core invariant. The model's text must never reach the user."""
        stub_model(
            answer="200 questions",
            found=True,
            quote_from_line=4,
            quote_to_line=4,
            # A paraphrase: comma dropped, synonym swapped.
            supporting_quote="இந்த வினாத்தொகுப்பு 200 வினாக்கள் உள்ளன.",
        )
        record = pipeline.ask(doc, "q")
        assert record.status is AnswerStatus.CITED
        assert record.quote == SOURCE_LINES[3]        # the document's words
        assert record.quote != record.model_claimed_quote  # not the model's
        assert record.quote in doc.text

    def test_model_paraphrase_is_flagged_but_not_fatal(self, doc, stub_model):
        stub_model(
            answer="a",
            found=True,
            quote_from_line=4,
            quote_to_line=4,
            supporting_quote="something else entirely",
        )
        record = pipeline.ask(doc, "q")
        assert record.status is AnswerStatus.CITED
        assert record.model_quote_matched is False

    def test_faithful_model_quote_is_recorded_as_matching(self, doc, stub_model):
        stub_model(
            answer="a",
            found=True,
            quote_from_line=4,
            quote_to_line=4,
            supporting_quote=SOURCE_LINES[3],
        )
        assert pipeline.ask(doc, "q").model_quote_matched is True

    def test_line_numbers_are_reported(self, doc, stub_model):
        stub_model(answer="a", found=True, quote_from_line=4, quote_to_line=5)
        record = pipeline.ask(doc, "q")
        assert (record.quote_from_line, record.quote_to_line) == (4, 5)


class TestModelSeesNumberedText:
    def test_the_document_is_passed_with_line_numbers(self, doc, monkeypatch):
        seen: dict[str, str] = {}

        def capture(numbered, question, **_):
            seen["numbered"] = numbered
            return ModelAnswer(answer="a", found=False)

        monkeypatch.setattr(pipeline, "ask_model", capture)
        pipeline.ask(doc, "q")

        # Without numbering the model cannot point at anything.
        assert "1 | " in seen["numbered"]
        assert SOURCE_LINES[0] in seen["numbered"]


class TestRefusalsAreHonestAboutWhy:
    """A limit of ours must never be reported as the document's silence.

    This shipped broken: a 15-line answer to "help me understand this
    notification" was refused by an 8-line cap, and the reader was told "this
    page doesn't say" -- about a page that said it plainly. That is worse than
    a hallucination, because they walk away believing the document lacks
    something it contains.
    """

    def test_document_silence_says_so(self, doc, stub_model):
        stub_model(answer="x", found=False)
        record = pipeline.ask(doc, "q")
        assert record.refusal_reason is RefusalReason.DOCUMENT_SILENT
        assert record.answer == "not stated in this document"

    def test_an_over_wide_range_is_answered_and_flagged(self, long_doc, stub_model):
        """Breadth stopped being a refusal. It is now a note on the answer.

        The old behaviour refused, honestly, with its own wording -- and the
        refusal itself was the problem: a verified citation was withheld
        because it was unimpressive. A reader asking "what is this page about?"
        got nothing, about a page that answers exactly that.
        """
        stub_model(answer="an overview", found=True, quote_from_line=1, quote_to_line=30)
        record = pipeline.ask(long_doc, "q")
        assert record.status is AnswerStatus.CITED
        assert record.refusal_reason is None
        assert record.citation_is_broad
        assert record.quote_line_count == 30

    def test_an_unresolvable_range_is_not_called_silence(self, doc, stub_model):
        stub_model(answer="x", found=True, quote_from_line=500, quote_to_line=500)
        record = pipeline.ask(doc, "q")
        assert record.refusal_reason is RefusalReason.CITATION_INVALID
        assert "not stated" not in record.answer

    def test_every_refusal_reason_has_distinct_wording(self):
        texts = [pipeline.REFUSAL_TEXT[reason] for reason in RefusalReason]
        # DOCUMENT_SILENT and NOT_RELEVANT deliberately share wording: both are
        # genuinely "the page does not answer this".
        assert len(set(texts)) == 2

    def test_no_refusal_reason_is_about_the_size_of_a_citation(self):
        # The remaining reasons are all about whether an answer exists or
        # whether it could be located. None is about how big it turned out.
        assert not any("broad" in reason.value for reason in RefusalReason)

    def test_a_proportionate_span_on_a_long_page_is_cited(self, long_doc, stub_model):
        # The case that shipped broken twice: a wide-but-reasonable summary.
        stub_model(answer="overview", found=True, quote_from_line=2, quote_to_line=9)
        record = pipeline.ask(long_doc, "q")
        assert record.status is AnswerStatus.CITED
        assert not record.citation_is_broad
