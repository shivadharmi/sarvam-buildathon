"""Data contract shared by the pipeline, the HTTP API, and the frontend.

All models are frozen: a stage produces a new record rather than mutating the
one it was handed, so an answer's provenance cannot be edited after the gate
has ruled on it.
"""

from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class Frozen(BaseModel):
    model_config = ConfigDict(frozen=True)


class AnswerStatus(str, Enum):
    """How much trust the answer has earned.

    There are only two states by design. There is no "low confidence" middle
    ground -- either a verbatim source span backs the answer, or the document
    does not say.
    """

    CITED = "cited"
    NOT_STATED = "not_stated"


class RefusalReason(str, Enum):
    """Why an answer was not cited.

    `status` says whether the answer stands. This says why it did not, and the
    distinction is not cosmetic: DOCUMENT_SILENT is a claim about the page,
    while the others are limits of ours. Reporting our own limit as the
    document's silence tells the reader the page lacks something it contains --
    the exact dishonesty this product exists to prevent.
    """

    DOCUMENT_SILENT = "document_silent"
    CITATION_TOO_BROAD = "citation_too_broad"
    CITATION_INVALID = "citation_invalid"
    NOT_RELEVANT = "not_relevant"


class DocOrigin(str, Enum):
    """Where a document came from. Builtin docs are pinned in the UI and are
    the offline demo fallback; uploads are reader-supplied and disposable."""

    BUILTIN = "builtin"
    UPLOAD = "upload"


class LanguageSource(str, Enum):
    """How we arrived at the language a document was digitised in.

    Surfaced in the UI rather than kept internal: a reader who can see we
    *guessed* the language can correct us, and a reader who can see we asked
    knows we did not guess. Detection is a claim about our own process, so it
    is held to the same standard as a claim about the document.
    """

    BUILTIN = "builtin"  # hardcoded for doc_a / doc_b
    DETECTED = "detected"  # /text-lid, corroborated by the script we can see
    SCRIPT = "script"  # LID disagreed; the script maps 1:1, so we overruled it
    USER = "user"  # ambiguous or unrecognised script — the reader told us


class StarterQuestion(Frozen):
    """A suggested opening question for a document.

    Model-authored *input*, never a citation. An answer to one still goes
    through the same line-anchored gate as anything the reader types.
    """

    text: str = Field(description="In the document's own language")
    gloss: str = Field(default="", description="English gloss, so a non-reader can follow")


class Block(Frozen):
    """One layout region of the page, as returned in the page-level JSON.

    Coordinates are included because the API does return them, contrary to the
    scope doc. Nothing renders them yet -- visual pins are a §7 parking-lot
    item -- but storing them costs nothing and keeps that door open.
    """

    reading_order: int
    layout_tag: str = Field(description='e.g. "header", "ordered-list", "sidebar"')
    confidence: float
    text: str

    x1: float
    y1: float
    x2: float
    y2: float

    # Where this block's text sits in DigitisedDoc.text, so a quote offset can
    # be resolved back to the region of the page it came from.
    start: int
    end: int


class DigitisedDoc(Frozen):
    """A page after digitisation. `text` is NFC-normalised and cached to disk.

    Quote offsets elsewhere in the system index into `text`, so it must be the
    exact string the frontend renders.

    `text` is assembled from `blocks` in reading order rather than taken from
    the Markdown output: the Markdown renumbers wrapped lines as new list
    items, which injects list markers into the middle of sentences and makes
    genuinely verbatim quotes unmatchable.
    """

    doc_id: str
    language: str = Field(description='Sarvam language code, e.g. "ta-IN"')
    text: str
    source_filename: str
    digitised_at: str
    page_count: int = 1
    blocks: tuple[Block, ...] = ()

    # Provenance of the document and of its language. Every field below is
    # defaulted on purpose: `doc_a.json` and `doc_b.json` are already on disk
    # and are the offline fallback for a dead API during the demo. A field
    # without a default would stop them deserialising.
    origin: DocOrigin = DocOrigin.BUILTIN
    label: str = Field(default="", description="Display name; for uploads, the original filename")
    language_source: LanguageSource = LanguageSource.BUILTIN
    probe_language: str = Field(
        default="",
        description="What the probe pass used, so a bad detection stays diagnosable",
    )

    def block_at(self, offset: int) -> Block | None:
        """The block containing a character offset, if any."""
        return next((b for b in self.blocks if b.start <= offset < b.end), None)


class ModelAnswer(Frozen):
    """Raw structured output from the QA model, before verification.

    The model points at a line range; it does not supply the citation text.
    `supporting_quote` is still requested, but only so we can notice when the
    model quotes something other than the lines it pointed at -- it is never
    the source of the citation shown to the user.
    """

    answer: str
    found: bool
    quote_from_line: int = 0
    quote_to_line: int = 0
    supporting_quote: str = ""


class NoteAcknowledgement(Frozen):
    """The reader told us something rather than asking something.

    Deliberately NOT an AnswerStatus. That enum describes what the *document*
    says, and there are only two such states by design. "Noted" is not a claim
    about the document at all, so it is a separate kind of turn -- which keeps
    the two-state guarantee exactly as narrow as it should be.
    """

    kind: Literal["note"] = "note"
    doc_id: str
    note: str
    acknowledgement: str = Field(description="Short reply in the reader's language")
    asked_at: str


class AnswerRecord(Frozen):
    """The final artifact: shareable and verifiable, not a chat message."""

    kind: Literal["answer"] = "answer"
    question: str
    answer: str
    status: AnswerStatus
    doc_id: str

    # The citation, extracted by us from the lines the model pointed at.
    quote: str | None = None
    quote_start: int | None = None
    quote_end: int | None = None
    quote_from_line: int | None = None
    quote_to_line: int | None = None

    model: str
    asked_at: str

    # Kept so the UI can show when the model asserted a source we could not
    # honour. This is the honesty story made visible, not debug noise.
    model_claimed_found: bool = False
    model_claimed_quote: str | None = None
    refusal_reason: RefusalReason | None = None
    rejection_detail: str | None = None

    # False when the model's own quote does not appear in the lines it cited --
    # it pointed one place and quoted another. The citation shown is always the
    # extracted lines, so this is a transparency signal, not a gate.
    model_quote_matched: bool | None = None

    @property
    def was_overruled(self) -> bool:
        """True when the model asserted a source and verification refused it."""
        return self.status is AnswerStatus.NOT_STATED and self.model_claimed_found


class Turn(Frozen):
    """One earlier exchange, replayed as a real user/assistant message pair.

    Carried so that "and the age limit?" can be understood. It informs what the
    question *means*; it can never supply the answer, because the citation is
    still sliced out of the document at a verified line range.

    The line numbers are kept so the assistant turn can be reconstructed in the
    same schema the model actually replies in, rather than as prose about it.
    """

    question: str = Field(max_length=500)
    answer: str = Field(max_length=2000)
    status: AnswerStatus
    quote_from_line: int = 0
    quote_to_line: int = 0


class Correction(Frozen):
    """A note the reader has given to help interpret the document.

    Reader-authored text. It may change which lines get cited, and it must
    never become a citation itself.
    """

    note: str = Field(min_length=1, max_length=300)


class AskRequest(Frozen):
    doc_id: str
    question: str = Field(min_length=1, max_length=500)

    # Client-held session state. The backend stores nothing between requests,
    # so reloading the page is a complete, reliable reset.
    history: tuple[Turn, ...] = ()
    corrections: tuple[Correction, ...] = ()
