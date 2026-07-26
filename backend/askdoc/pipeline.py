"""Join the model's claim to deterministic verification, producing an AnswerRecord.

This is the only place an answer is allowed to become "cited". Note what does
NOT appear below: any path where text written by the model becomes the citation
shown to the user. The citation is always sliced out of our own copy of the
document, at line numbers the model pointed to.

`claim.found` is trusted in one direction only. A "no" is honoured immediately,
because refusing is the safe direction. A "yes" earns nothing until the line
range survives verification.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Sequence

from .config import NOT_STATED, QA_MODEL, RELEVANCE_CHECK, UNVERIFIED
from .gate import check_quote
from .lines import extract_lines, render_numbered
from .intent import classify
from .models import (
    AnswerRecord,
    AnswerStatus,
    Correction,
    DigitisedDoc,
    NoteAcknowledgement,
    RefusalReason,
    Turn,
)
from .qa import ask_model
from .relevance import is_relevant


# Each failure gets its own words. See config for why they must stay distinct.
REFUSAL_TEXT = {
    RefusalReason.DOCUMENT_SILENT: NOT_STATED,
    RefusalReason.NOT_RELEVANT: NOT_STATED,
    RefusalReason.CITATION_INVALID: UNVERIFIED,
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def handle(
    doc: DigitisedDoc,
    message: str,
    *,
    history: Sequence[Turn] = (),
    corrections: Sequence[Correction] = (),
) -> AnswerRecord | NoteAcknowledgement:
    """Answer a question, or remember something the reader told us.

    One input box means deciding per message which of those it is. See
    `intent.py` for why that decision is biased toward answering.
    """
    is_question, acknowledgement = classify(message)

    if not is_question:
        return NoteAcknowledgement(
            doc_id=doc.doc_id,
            note=message,
            acknowledgement=acknowledgement or "Noted.",
            asked_at=_now(),
        )

    return ask(doc, message, history=history, corrections=corrections)


def ask(
    doc: DigitisedDoc,
    question: str,
    *,
    history: Sequence[Turn] = (),
    corrections: Sequence[Correction] = (),
) -> AnswerRecord:
    """Answer a question about one document, or honestly decline.

    `history` and `corrections` are reader-supplied context. They can change
    which lines the model points at -- that is what makes follow-up questions
    and corrections work -- but they can never become the citation, because
    the citation is sliced out of `doc.text` at a verified line range.
    """
    claim = ask_model(
        render_numbered(doc.text),
        question,
        history=history,
        corrections=corrections,
    )

    common = {
        "question": question,
        "doc_id": doc.doc_id,
        "model": QA_MODEL,
        "asked_at": _now(),
        "model_claimed_found": claim.found,
        "model_claimed_quote": claim.supporting_quote or None,
    }

    def refuse(reason: RefusalReason, detail: str) -> AnswerRecord:
        # Only DOCUMENT_SILENT may be shown as "the page doesn't say". The
        # others are our limits, and calling them silence would tell the
        # reader the page lacks something it actually contains.
        return AnswerRecord(
            answer=REFUSAL_TEXT[reason],
            status=AnswerStatus.NOT_STATED,
            refusal_reason=reason,
            rejection_detail=detail,
            **common,
        )

    if not claim.found:
        return refuse(
            RefusalReason.DOCUMENT_SILENT,
            "the model reported the document does not state this",
        )

    span = extract_lines(doc.text, claim.quote_from_line, claim.quote_to_line)
    if not span.valid:
        # Only unresolvable ranges refuse now. Width does not: a wide citation
        # is weaker evidence, not false evidence, and throwing away a verified
        # answer to avoid an unimpressive citation costs the reader far more
        # than it protects them.
        return refuse(
            RefusalReason.CITATION_INVALID,
            span.reason or "the cited lines could not be resolved",
        )

    # The citation is real. Separately: does it actually answer the question?
    # Verification cannot tell us that, so we ask a judge that sees only the
    # question and this passage. Failing here refuses rather than misleads.
    if RELEVANCE_CHECK:
        relevant, why = is_relevant(question, span.text)
        if not relevant:
            return refuse(RefusalReason.NOT_RELEVANT, why)

    # Did the model quote the lines it actually pointed at? Purely a
    # transparency signal -- the citation below is the extracted span either
    # way, so a mismatch cannot put invented text in front of the user.
    quote_matched = (
        check_quote(claim.supporting_quote, span.text).passed
        if claim.supporting_quote
        else None
    )

    return AnswerRecord(
        answer=claim.answer,
        status=AnswerStatus.CITED,
        quote=span.text,
        quote_start=span.start,
        quote_end=span.end,
        quote_from_line=claim.quote_from_line,
        quote_to_line=claim.quote_to_line,
        quote_line_count=span.line_count,
        citation_is_broad=span.broad,
        model_quote_matched=quote_matched,
        **common,
    )
