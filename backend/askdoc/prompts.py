"""The grounded-QA prompt and its forced output schema.

The prompt asks the model to behave; the gate in `gate.py` enforces it. Treat
everything here as best-effort steering -- never as a guarantee. If this prompt
and the gate ever disagree, the gate wins.
"""

from __future__ import annotations

import json
from typing import Sequence

from .models import AnswerStatus, Correction, Turn

# Sent via response_format={"type": "json_schema", "json_schema": ANSWER_SCHEMA}.
# `strict` makes the three fields mandatory, which stops the model from
# answering without at least attempting a citation.
ANSWER_SCHEMA = {
    "name": "grounded_answer",
    "strict": True,
    "schema": {
        "type": "object",
        "properties": {
            "answer": {
                "type": "string",
                "description": "Plain-language answer, in the language of the question.",
            },
            "found": {
                "type": "boolean",
                "description": "Whether the document actually answers the question.",
            },
            "quote_from_line": {
                "type": "integer",
                "description": (
                    "First line number of the passage that proves the answer. "
                    "0 if the document does not say."
                ),
            },
            "quote_to_line": {
                "type": "integer",
                "description": (
                    "Last line number of that passage (same as quote_from_line "
                    "for a single line). 0 if the document does not say."
                ),
            },
            "supporting_quote": {
                "type": "string",
                "description": (
                    "The text on those lines, in the document's ORIGINAL SCRIPT "
                    "AND LANGUAGE. Used only as a cross-check; the citation "
                    "shown to the user is taken from the line numbers."
                ),
            },
        },
        "required": [
            "answer",
            "found",
            "quote_from_line",
            "quote_to_line",
            "supporting_quote",
        ],
        "additionalProperties": False,
    },
}


SYSTEM_PROMPT = """\
You answer questions about ONE official document, using ONLY the text of that \
document.

The document is shown to you with a line number at the start of every line, in \
the form:

     7 | some text on line seven

You do NOT write out the citation. You POINT at it, by giving the line numbers \
where the supporting passage appears. The text of those lines is then taken \
directly from the document, so you cannot misquote it and you do not need to \
reproduce it perfectly.

Rules:

1. Use ONLY the document text supplied below. You have no other knowledge of \
this document, this organisation, or this scheme. If you happen to know \
something about this subject from elsewhere, you must NOT use it.

2. Set `quote_from_line` and `quote_to_line` to the SMALLEST range of lines \
that actually proves your answer. One line is best. A citation that covers \
everything proves nothing, so never point at the whole document when a part \
of it will do.

But do not refuse a question because the answer is spread out. If someone \
asks what the page is about, or asks for a summary, the honest citation IS \
the wide one -- point at the whole run of lines that carries the answer, and \
say so.

3. The line numbers are the part that matters. Read them carefully off the \
left margin and make sure the passage you mean really is on those lines.

4. If the document does not answer the question, set `found` to false, set \
both line numbers to 0, and say plainly in `answer` that this document does \
not state it. A question being reasonable, or the answer being something you \
could guess, is NOT a reason to answer it. Refusing correctly is a good \
outcome, not a failure.

5. Write `answer` in the same language the question was asked in.

6. Fill `supporting_quote` with the text you believe is on those lines, in the \
document's ORIGINAL SCRIPT AND LANGUAGE -- never translated. This is only a \
cross-check on your line numbers; it is not what gets shown.\
"""

# Appended only when there is actually a conversation. Adding it to a
# first-turn prompt measurably hurt accuracy -- it introduces rules about
# something that is not happening, and dilutes the ones that matter.
FOLLOWUP_RULE = """

7. A later question may refer back to an earlier one ("and the age limit?", \
"what about that fee?"). Use the conversation to understand what is being \
asked. But your own earlier answers are NOT a source: every answer, including \
a follow-up, must point at lines in the document.\
"""


def _corrections_block(corrections: Sequence[Correction]) -> str:
    """Reader-supplied interpretation notes, appended to the system message.

    They live in the system turn rather than a user turn because they apply to
    the whole session and the reader can add one at any point -- the message
    list is rebuilt per request, so the newest set always applies.
    """
    if not corrections:
        return ""

    lines = [
        "",
        "",
        "<what_the_reader_told_you>",
        "The reader has told you the following. Treat every one of these as "
        "TRUE and apply it. They describe the reader's own situation and how "
        "to read this document -- things you could not work out on your own.",
        "",
    ]
    lines.extend(f"- {correction.note}" for correction in corrections)
    lines.append("</what_the_reader_told_you>")
    lines.append(
        "When a question depends on one of these, apply it directly and answer. "
        "Do NOT ask the reader to tell you again -- they already have. For "
        'example, if they told you which office or project they belong to, then '
        '"my project" means that one, and you should point at the line for it.'
    )
    lines.append(
        "IMPORTANT: you may have declined a question earlier in this "
        "conversation, before the reader told you these things. If one of "
        "these statements supplies exactly what was missing, answer the "
        "question NOW instead of declining again. Do not repeat an earlier "
        "refusal just because you gave one."
    )
    lines.append(
        "The one limit: a citation is always lines from the document. Never "
        "point at, or quote, one of these statements."
    )
    return "\n".join(lines)


def _first_user_turn(numbered_document: str, question: str) -> str:
    return (
        "<document>\n"
        f"{numbered_document}\n"
        "</document>\n\n"
        "Answer this question using only the document above. "
        "Point at the line numbers that prove your answer.\n\n"
        f"Question: {question}"
    )


def _assistant_turn(turn: Turn) -> str:
    """Rebuild an earlier reply in the schema the model actually answers in.

    Reconstructed from the *verified* record rather than the model's original
    claim: that is what the reader was shown, so it is what the conversation
    should reflect.
    """
    cited = turn.status is AnswerStatus.CITED
    return json.dumps(
        {
            "answer": turn.answer,
            "found": cited,
            "quote_from_line": turn.quote_from_line if cited else 0,
            "quote_to_line": turn.quote_to_line if cited else 0,
            "supporting_quote": "",
        },
        ensure_ascii=False,
    )


def build_messages(
    numbered_document: str,
    question: str,
    *,
    history: Sequence[Turn] = (),
    corrections: Sequence[Correction] = (),
) -> list[dict[str, str]]:
    """Assemble the full message list for one question.

    A real multi-turn conversation, not a narrated transcript stuffed into one
    user message: earlier exchanges are replayed as actual user/assistant
    pairs, which is the shape the model is trained on and what lets a
    follow-up like "and the age limit?" resolve.

    The document appears once, in the first user turn, and stays in context
    for the rest of the session.
    """
    # A refusal recorded before the reader added a note is stale: it was given
    # without information they have since supplied. Replaying it anchors the
    # model into repeating itself -- measured at 3/3, and no amount of prompt
    # instruction moved it. So drop those turns rather than argue with them.
    # Cited turns are kept: a real citation does not go stale.
    if corrections:
        history = [turn for turn in history if turn.status is AnswerStatus.CITED]

    system = SYSTEM_PROMPT
    if history:
        system += FOLLOWUP_RULE
    system += _corrections_block(corrections)

    messages = [{"role": "system", "content": system}]

    if not history:
        messages.append({"role": "user", "content": _first_user_turn(numbered_document, question)})
        return messages

    first, *rest = history
    messages.append(
        {"role": "user", "content": _first_user_turn(numbered_document, first.question)}
    )
    messages.append({"role": "assistant", "content": _assistant_turn(first)})

    for turn in rest:
        messages.append({"role": "user", "content": f"Question: {turn.question}"})
        messages.append({"role": "assistant", "content": _assistant_turn(turn)})

    messages.append({"role": "user", "content": f"Question: {question}"})
    return messages
