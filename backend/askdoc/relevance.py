"""Second, independent check: does the cited passage actually answer the question?

Verification in `lines.py` guarantees a citation is *real*. It cannot
guarantee it is *relevant* -- the model can point at genuine verbatim text
that answers a different question. That is a retrieval failure, and no string
or line check can detect it.

This module closes that gap the only way it can be closed: by asking again,
with a deliberately narrow view.

Two design choices make this a genuine second opinion rather than a rubber
stamp:

1. **The judge sees ONLY the question and the cited passage** -- never the
   whole document. It cannot go and find a better passage, so it cannot
   rationalise; it can only rule on what was actually cited.
2. **Uncertainty resolves to "not relevant"**, which downgrades the answer to
   an honest refusal. The failure direction is silence, never a confident
   wrong citation.
"""

from __future__ import annotations

from .sarvam_http import ChatError
from .structured import complete_structured

# `reason` is deliberately FIRST. The model must articulate its judgement
# before committing to the boolean, which improves the verdict and avoids the
# degeneration observed when sarvam-105b had to emit `false` immediately.
RELEVANCE_SCHEMA = {
    "name": "relevance_verdict",
    "description": "Record whether the passage answers the question.",
    "strict": True,
    "schema": {
        "type": "object",
        "properties": {
            "reason": {
                "type": "string",
                "description": (
                    "One short sentence: what the question asks for, and "
                    "whether this passage contains it."
                ),
            },
            "answers_the_question": {
                "type": "boolean",
                "description": (
                    "True only if this exact passage contains the information "
                    "the question asks for."
                ),
            },
        },
        "required": ["reason", "answers_the_question"],
        "additionalProperties": False,
    },
}

JUDGE_PROMPT = """\
You are checking for one specific failure: the passage below was retrieved for \
the question below, but it may be about a COMPLETELY DIFFERENT topic.

Your job is to catch that clear mismatch, and nothing else.

Say **false** only when the passage is plainly about something else -- when a \
reader would say "this is not what I asked about at all". Typically this is \
when the passage merely shares a word or root with the question but discusses \
an unrelated matter.

Say **true** in every other case, including when:
- the passage answers the question only partly, or indirectly
- it contains the answer alongside other unrelated material
- the wording differs from the question's wording
- it is awkwardly phrased, is an incomplete sentence, or reads oddly because \
it was cut from a longer document

IMPORTANT: the passage is in the document's original language, usually Tamil \
or Telugu. Judge it in that language. Do NOT translate it to English and then \
reason about the translation -- a translation slip would make you reject a \
passage that is actually correct.

You are a safety net for obvious retrieval mistakes, not a quality reviewer. \
When genuinely torn, say true.\
"""


def is_relevant(question: str, passage: str) -> tuple[bool, str]:
    """Return whether `passage` answers `question`, and why.

    On any API or parsing failure this returns True: the relevance check is a
    refinement, and an infrastructure problem should not silently start
    refusing answers whose citations verified correctly.
    """
    messages = [
        {"role": "system", "content": JUDGE_PROMPT},
        {
            "role": "user",
            "content": (
                f"Question: {question}\n\n"
                f"Passage:\n<passage>\n{passage}\n</passage>\n\n"
                "Does this passage contain the information the question asks for?"
            ),
        },
    ]

    try:
        verdict = complete_structured(messages, RELEVANCE_SCHEMA)
        return bool(verdict["answers_the_question"]), str(verdict.get("reason", ""))
    except (ChatError, KeyError, TypeError):
        return True, "relevance check unavailable"
