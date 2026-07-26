"""Suggested opening questions for a document.

A dense official page gives a reader nothing to grab onto: they can see it
matters and cannot see what to ask. Three or four questions the page actually
answers turn an empty box into a starting point.

These are model-authored **input**, and they buy no trust. A starter is exactly
as trusted as a question the reader types -- which is to say, not at all:
answering one runs the same line-anchored gate, and the citation is still
sliced out of our own copy of the text. Nothing written here can become a
citation. `tests/test_starters.py::TestAGeneratedQuestionIsNeverACitation`
pins that.

Every failure returns `()`. A page with no suggestions is a plain input box; a
page that cannot be opened because its suggestions failed is a broken product.
So this module does not raise at its caller, ever.
"""

from __future__ import annotations

from . import cache
from .models import DigitisedDoc, StarterQuestion
from .structured import complete_structured

# Asked for as 3-4 and trimmed to 4. More than a handful buries the input box,
# which is the thing we actually want the reader to use.
MIN_STARTERS = 3
MAX_STARTERS = 4

STARTERS_SCHEMA = {
    "name": "starter_questions",
    "description": "Suggest opening questions this page can answer.",
    "strict": True,
    "schema": {
        "type": "object",
        "properties": {
            "questions": {
                "type": "array",
                "minItems": MIN_STARTERS,
                "maxItems": MAX_STARTERS,
                "items": {
                    "type": "object",
                    "properties": {
                        "text": {
                            "type": "string",
                            "description": (
                                "The question, in the document's ORIGINAL SCRIPT "
                                "AND LANGUAGE. Never translate it to English -- "
                                "it is written for someone reading this page."
                            ),
                        },
                        "gloss": {
                            "type": "string",
                            "description": (
                                "The same question in short, plain English, for "
                                "someone who cannot read that script."
                            ),
                        },
                    },
                    "required": ["text", "gloss"],
                    "additionalProperties": False,
                },
            }
        },
        "required": ["questions"],
        "additionalProperties": False,
    },
}

STARTERS_PROMPT = """\
A reader has opened one official document that they find hard to read, and \
needs somewhere to start.

Suggest 3 or 4 short questions that THIS page can actually answer, working \
only from the text below.

Rules:

1. Every question must be answerable from the text shown. Do not suggest one \
just because a document of this kind usually answers it. An inviting question \
the page cannot answer only teaches the reader that the answers are unreliable.

2. Ask about what a reader comes to a page like this for: dates, amounts, \
eligibility, what they have to do, and what happens if they do not.

3. Write `text` in the document's OWN SCRIPT AND LANGUAGE -- the same script \
as the text below. Never translate it to English.

4. Write `gloss` as a short English rendering of that same question, for \
someone who cannot read that script.

5. Keep each one short and plain: a sentence a person would really type.\
"""


def _parse(data: dict) -> tuple[StarterQuestion, ...]:
    """Read questions out of the model's payload, dropping unusable entries.

    Raises rather than returning a partial guess when the payload is not the
    shape we asked for -- `generate` turns that into `()`. Validation is doing
    real work here: the API happily returns valid JSON with required fields
    silently missing.
    """
    questions = [
        question
        for question in (StarterQuestion.model_validate(item) for item in data["questions"])
        if question.text.strip()
    ]
    return tuple(questions[:MAX_STARTERS])


def generate(doc: DigitisedDoc) -> tuple[StarterQuestion, ...]:
    """Suggested questions for `doc`, generated on first request and cached.

    Returns `()` if anything at all goes wrong. The caller shows a plain input
    box and the reader loses a convenience, not the document.
    """
    if not doc.text.strip():
        # Nothing to ask about, and no reason to spend a paid call proving it.
        return ()

    try:
        cached = cache.load_starters(doc.doc_id)
        if cached is not None:
            return cached

        questions = _parse(
            complete_structured(
                [
                    {"role": "system", "content": STARTERS_PROMPT},
                    {
                        "role": "user",
                        "content": f"<document>\n{doc.text}\n</document>",
                    },
                ],
                STARTERS_SCHEMA,
            )
        )
    except Exception:
        # Deliberately broad. Anything from a 403 to a corrupt cache file to a
        # shape nobody anticipated has the same right answer here, and none of
        # them is worth failing a document over.
        return ()

    if not questions:
        return ()

    # Only a real set is written. An empty result is a failure worth retrying,
    # not a verdict that this page has nothing worth asking.
    try:
        cache.save_starters(doc.doc_id, questions)
    except OSError:
        # An unwritable cache costs one extra call next time, not correctness.
        pass

    return questions
