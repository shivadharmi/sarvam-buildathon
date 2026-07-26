"""Is this message a question about the document, or something the reader is telling us?

One input box is the natural interface -- a reader should not have to know
which field a thought belongs in. That means working out, per message, whether
to answer it or remember it.

**The classifier is biased toward answering.** Misreading a question as a
statement swallows it silently: the reader gets "noted" and never learns the
page had an answer. Misreading a statement as a question produces a refusal,
which is visible on screen and trivially recovered from. When in doubt, answer.
"""

from __future__ import annotations

from .sarvam_http import ChatError
from .structured import complete_structured

QUESTION_MARKS = ("?", "？", "।")

INTENT_SCHEMA = {
    "name": "message_intent",
    "description": "Classify what the reader's message is doing.",
    "strict": True,
    "schema": {
        "type": "object",
        "properties": {
            "reason": {
                "type": "string",
                "description": "One short sentence on what the message is doing.",
            },
            "is_a_question": {
                "type": "boolean",
                "description": (
                    "True if the reader is asking something about the document. "
                    "False ONLY if they are plainly telling you about themselves "
                    "or their situation."
                ),
            },
            "acknowledgement": {
                "type": "string",
                "description": (
                    "If it is not a question: one short sentence, IN THE READER'S "
                    "OWN LANGUAGE, confirming what you have noted. Empty otherwise."
                ),
            },
        },
        "required": ["reason", "is_a_question", "acknowledgement"],
        "additionalProperties": False,
    },
}

CLASSIFY_PROMPT = """\
A reader is looking at an official document and has typed a message. Decide \
what the message is doing.

Answer **true** (it is a question) when they are asking anything about the \
document -- a fact, a date, an amount, a rule, or a follow-up like "and the \
age limit?".

Answer **false** (it is a statement) ONLY when they are plainly telling you \
about themselves or their situation, with nothing being asked. For example: \
"I am applying to the Maldakal project", "I am in the ST category", "I want \
the helper post".

If you are unsure, answer **true**. Answering a statement by mistake merely \
produces a visible "this page doesn't say", which the reader can see and \
correct. Treating a real question as a statement silently loses it, and they \
may never realise the page could have answered them.

When it is a statement, write `acknowledgement` in the SAME LANGUAGE the \
reader used -- one short sentence confirming what you noted. Never translate \
it to English.\
"""


def looks_like_a_question(message: str) -> bool:
    """Cheap check that skips the classifier for the overwhelmingly common case.

    Almost every typed question ends in a question mark, so this keeps the
    normal path at one model call instead of two.
    """
    return message.strip().endswith(QUESTION_MARKS)


def classify(message: str) -> tuple[bool, str]:
    """Return (is_a_question, acknowledgement).

    Any failure resolves to "question", so a classifier outage degrades to the
    behaviour we had before rather than swallowing input.
    """
    if looks_like_a_question(message):
        return True, ""

    try:
        verdict = complete_structured(
            [
                {"role": "system", "content": CLASSIFY_PROMPT},
                {"role": "user", "content": f"The reader typed:\n\n{message}"},
            ],
            INTENT_SCHEMA,
        )
    except (ChatError, KeyError, TypeError):
        return True, ""

    is_question = bool(verdict.get("is_a_question", True))
    return is_question, str(verdict.get("acknowledgement", "")).strip()
