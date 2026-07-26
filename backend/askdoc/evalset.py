"""Labelled cases with ground truth, for measuring changes instead of guessing.

`must_contain` is a distinctive fragment of the passage that genuinely answers
the question. Checking it is how we detect the *relevance* failure that the
citation gate cannot catch: a case can be CITED, fully verbatim, and still
wrong because the model pointed at the wrong part of the page.

Ground truth was read off the source images by hand, not taken from model
output -- otherwise this would measure agreement, not correctness.
"""

from __future__ import annotations

from dataclasses import dataclass

from .models import AnswerStatus


@dataclass(frozen=True)
class Case:
    doc_id: str
    question: str
    expect: AnswerStatus
    must_contain: str | None = None
    note: str = ""

    @property
    def label(self) -> str:
        return self.question[:52]


CASES: tuple[Case, ...] = (
    # --- Doc A: TNPSC Tamil question-booklet cover -------------------------
    Case(
        doc_id="doc_a",
        question="இந்த வினாத்தொகுப்பில் எத்தனை வினாக்கள் உள்ளன?",
        expect=AnswerStatus.CITED,
        must_contain="200 வினாக்களைக்",
        note="instruction 2, near the top",
    ),
    Case(
        doc_id="doc_a",
        question="விடை தெரியவில்லை என்றால் நான் என்ன செய்ய வேண்டும்?",
        expect=AnswerStatus.CITED,
        must_contain="(E) என்பதை",
        note="line 48 of 65 -- the known relevance failure. Decoy: the "
        "defect-reporting instruction shares the தெரி- root.",
    ),
    Case(
        doc_id="doc_a",
        question="விடைத்தாளை நிரப்ப எந்த வகையான பேனாவைப் பயன்படுத்த வேண்டும்?",
        expect=AnswerStatus.CITED,
        must_contain="Black Ink Ball Point Pen",
        note="mixed Tamil/Latin script inside one span",
    ),
    Case(
        doc_id="doc_a",
        question="வினாத்தொகுப்பு எண்ணை எழுதாவிட்டால் என்ன ஆகும்?",
        expect=AnswerStatus.CITED,
        must_contain="ஐந்து மதிப்பெண்கள்",
        note="previously lost to a one-character paraphrase",
    ),
    Case(
        doc_id="doc_a",
        question="தேர்வின் கால அளவு எவ்வளவு?",
        expect=AnswerStatus.CITED,
        must_contain="மூன்று மணி நேரம்",
        note="two-column header with unbalanced brackets",
    ),
    Case(
        doc_id="doc_a",
        question="இந்தத் தேர்வில் தேர்ச்சி பெற எத்தனை மதிப்பெண்கள் தேவை?",
        expect=AnswerStatus.NOT_STATED,
        note="REFUSAL. Page is saturated with mark numbers (300/150/5) but "
        "states no cut-off. Strong pull toward inventing one.",
    ),
    Case(
        doc_id="doc_a",
        question="தேர்வு மையம் சென்னையில் எந்த முகவரியில் உள்ளது?",
        expect=AnswerStatus.NOT_STATED,
        note="REFUSAL. The page names no place at all.",
    ),
    # --- Doc B: Telangana Anganwadi Telugu notification --------------------
    Case(
        doc_id="doc_b",
        question="దరఖాస్తు చేసుకోవడానికి చివరి తేదీ ఎప్పుడు?",
        expect=AnswerStatus.CITED,
        must_contain="08/07/2026",
    ),
    Case(
        doc_id="doc_b",
        question="అభ్యర్థుల వయస్సు ఎంత ఉండాలి?",
        expect=AnswerStatus.CITED,
        must_contain="35",
    ),
    Case(
        doc_id="doc_b",
        question="విద్యార్హత ఏమిటి?",
        expect=AnswerStatus.CITED,
        must_contain="ఇంటర్",
    ),
    Case(
        doc_id="doc_b",
        question="దరఖాస్తు రుసుము ఎంత?",
        expect=AnswerStatus.NOT_STATED,
        note="REFUSAL. Third-party job sites publish a fee for these posts, "
        "so this tests that training knowledge does not leak in.",
    ),
    Case(
        doc_id="doc_b",
        question="అంగన్‌వాడీ టీచర్‌కు నెలవారీ గౌరవ వేతనం ఎంత?",
        expect=AnswerStatus.NOT_STATED,
        note="REFUSAL. Honorarium is also published elsewhere, absent here.",
    ),
)
