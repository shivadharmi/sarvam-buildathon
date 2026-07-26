"""Follow-up questions and reader corrections.

Two things are pinned here:

1. History is replayed as a real multi-turn conversation -- alternating
   user/assistant messages -- not flattened into prose inside one user turn.
2. Neither history nor a reader note can become a citation. They may change
   which lines get pointed at; they can never change what the citation says.
"""

import json

import pytest

from askdoc import cache, pipeline
from askdoc.models import AnswerStatus, Correction, ModelAnswer, Turn
from askdoc.prompts import build_messages

DOC_LINE = "2. இந்த வினாத்தொகுப்பு, 200 வினாக்களைக் கொண்டுள்ளது."
NUMBERED = "1 | " + DOC_LINE


def cited_turn(question="what is the age?", answer="18", lines=(4, 4)):
    return Turn(
        question=question,
        answer=answer,
        status=AnswerStatus.CITED,
        quote_from_line=lines[0],
        quote_to_line=lines[1],
    )


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
                "text": DOC_LINE,
                "coordinates": {"x1": 0, "y1": 0, "x2": 10, "y2": 10},
            }
        ],
        source_filename="doc_a_page.png",
    )


class TestConversationShape:
    def test_a_first_question_is_system_plus_one_user_turn(self):
        messages = build_messages(NUMBERED, "how many?")
        assert [m["role"] for m in messages] == ["system", "user"]

    def test_history_becomes_alternating_user_and_assistant_turns(self):
        messages = build_messages(
            NUMBERED,
            "and the fee?",
            history=[cited_turn(), cited_turn(question="qualification?", answer="Inter")],
        )
        assert [m["role"] for m in messages] == [
            "system",
            "user",
            "assistant",
            "user",
            "assistant",
            "user",
        ]

    def test_the_document_appears_once_in_the_first_user_turn(self):
        messages = build_messages(
            NUMBERED, "follow up", history=[cited_turn(), cited_turn()]
        )
        carrying = [m for m in messages if "<document>" in m["content"]]
        assert len(carrying) == 1
        assert carrying[0] is messages[1]

    def test_the_current_question_is_the_final_user_turn(self):
        messages = build_messages(NUMBERED, "MY QUESTION", history=[cited_turn()])
        assert messages[-1]["role"] == "user"
        assert "MY QUESTION" in messages[-1]["content"]

    def test_the_first_history_question_is_not_lost(self):
        messages = build_messages(NUMBERED, "next", history=[cited_turn("original?")])
        assert "original?" in messages[1]["content"]


class TestAssistantTurnReconstruction:
    def test_earlier_reply_is_replayed_in_the_answer_schema(self):
        messages = build_messages(NUMBERED, "next", history=[cited_turn(lines=(4, 6))])
        replayed = json.loads(messages[2]["content"])
        assert replayed["found"] is True
        assert (replayed["quote_from_line"], replayed["quote_to_line"]) == (4, 6)

    def test_an_earlier_refusal_is_replayed_as_not_found(self):
        messages = build_messages(
            NUMBERED,
            "next",
            history=[
                Turn(question="fee?", answer="not stated", status=AnswerStatus.NOT_STATED)
            ],
        )
        replayed = json.loads(messages[2]["content"])
        assert replayed["found"] is False
        assert replayed["quote_from_line"] == 0

    def test_replayed_turns_keep_the_original_script(self):
        messages = build_messages(NUMBERED, "next", history=[cited_turn(answer=DOC_LINE)])
        assert DOC_LINE in messages[2]["content"]


class TestCorrections:
    def test_notes_ride_on_the_system_message(self):
        messages = build_messages(
            NUMBERED, "q", corrections=[Correction(note="ஆயா means the helper post")]
        )
        assert "ஆயா means the helper post" in messages[0]["content"]

    def test_notes_may_not_be_quoted_as_a_citation(self):
        messages = build_messages(NUMBERED, "q", corrections=[Correction(note="n")])
        system = messages[0]["content"]
        assert "Never point at, or quote, one of these statements." in system

    def test_no_notes_block_when_there_are_none(self):
        assert "what_the_reader_told_you" not in build_messages(NUMBERED, "q")[0]["content"]


class TestContextCannotBecomeACitation:
    def test_a_correction_is_never_quoted(self, doc, monkeypatch):
        """The core boundary. A note steers retrieval; it never supplies text."""
        invented = "The fee is Rs. 500 according to my note."

        monkeypatch.setattr(
            pipeline,
            "ask_model",
            lambda *_, **__: ModelAnswer(
                answer=invented,
                found=True,
                quote_from_line=1,
                quote_to_line=1,
                supporting_quote=invented,
            ),
        )

        record = pipeline.ask(
            doc, "what is the fee?", corrections=[Correction(note=invented)]
        )

        assert record.quote == DOC_LINE
        assert invented not in (record.quote or "")
        assert record.quote in doc.text

    def test_a_correction_cannot_rescue_an_invalid_line_range(self, doc, monkeypatch):
        monkeypatch.setattr(
            pipeline,
            "ask_model",
            lambda *_, **__: ModelAnswer(
                answer="the note says 500", found=True, quote_from_line=99, quote_to_line=99
            ),
        )
        record = pipeline.ask(doc, "q", corrections=[Correction(note="fee is 500")])
        assert record.status is AnswerStatus.NOT_STATED

    def test_context_is_threaded_through_to_the_model(self, doc, monkeypatch):
        seen: dict[str, object] = {}

        def capture(numbered, question, *, history=(), corrections=()):
            seen["history"], seen["corrections"] = history, corrections
            return ModelAnswer(answer="x", found=False)

        monkeypatch.setattr(pipeline, "ask_model", capture)

        turns = (cited_turn(),)
        notes = (Correction(note="n"),)
        pipeline.ask(doc, "q", history=turns, corrections=notes)

        assert seen["history"] == turns
        assert seen["corrections"] == notes


class TestFollowupRuleIsConditional:
    """Rules about a conversation that isn't happening measurably hurt accuracy."""

    def test_absent_on_a_first_question(self):
        assert "refer back to an earlier one" not in build_messages(NUMBERED, "q")[0]["content"]

    def test_present_once_there_is_history(self):
        messages = build_messages(NUMBERED, "q", history=[cited_turn()])
        assert "refer back to an earlier one" in messages[0]["content"]


class TestNotesAreFramedToBeUsed:
    """Over-fencing silently disabled this feature once; keep it fixed.

    Three consecutive negatives ("NOT part of the document", "never point at
    them", "never let a note alone be your answer") taught the model to treat
    reader notes as untrustworthy noise -- it kept asking the reader to repeat
    information they had already given. The constraint is real, but it has to
    come after the instruction, not drown it.
    """

    def test_notes_are_asserted_as_true(self):
        system = build_messages(
            NUMBERED, "q", corrections=[Correction(note="I applied to Maldakal")]
        )[0]["content"]
        assert "TRUE" in system

    def test_the_model_is_told_not_to_ask_again(self):
        system = build_messages(NUMBERED, "q", corrections=[Correction(note="n")])[0][
            "content"
        ]
        assert "Do NOT ask the reader to tell you again" in system

    def test_the_citation_limit_still_stands(self):
        system = build_messages(NUMBERED, "q", corrections=[Correction(note="n")])[0][
            "content"
        ]
        assert "a citation is always lines from the document" in system

    def test_the_instruction_precedes_the_limit(self):
        # Ordering is the whole lesson: apply-this first, constraint second.
        system = build_messages(NUMBERED, "q", corrections=[Correction(note="n")])[0][
            "content"
        ]
        assert system.index("Treat every one of these as") < system.index("The one limit")


class TestStaleRefusalsAreDropped:
    """A refusal given before the reader added a note is out-of-date evidence.

    Replaying it anchored the model into repeating the refusal even when a note
    now supplied exactly what had been missing -- measured 3/3, and explicit
    prompt instruction ("do not repeat an earlier refusal") did not move it.
    So the stale turn is removed rather than argued with.
    """

    def test_a_refusal_is_dropped_once_a_note_exists(self):
        refusal = Turn(question="my project?", answer="not stated", status=AnswerStatus.NOT_STATED)
        messages = build_messages(
            NUMBERED, "my project?", history=[refusal], corrections=[Correction(note="Maldakal")]
        )
        assert [m["role"] for m in messages] == ["system", "user"]

    def test_a_refusal_is_kept_when_there_are_no_notes(self):
        refusal = Turn(question="fee?", answer="not stated", status=AnswerStatus.NOT_STATED)
        messages = build_messages(NUMBERED, "next", history=[refusal])
        assert [m["role"] for m in messages] == ["system", "user", "assistant", "user"]

    def test_cited_turns_survive_because_a_citation_does_not_go_stale(self):
        messages = build_messages(
            NUMBERED, "next", history=[cited_turn()], corrections=[Correction(note="n")]
        )
        assert [m["role"] for m in messages] == ["system", "user", "assistant", "user"]

    def test_the_document_still_appears_exactly_once_after_dropping(self):
        refusal = Turn(question="a", answer="b", status=AnswerStatus.NOT_STATED)
        messages = build_messages(
            NUMBERED, "q", history=[refusal, cited_turn()], corrections=[Correction(note="n")]
        )
        assert len([m for m in messages if "<document>" in m["content"]]) == 1
