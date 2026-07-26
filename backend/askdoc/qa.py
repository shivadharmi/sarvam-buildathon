"""Grounded QA: ask the model where the answer is.

The model points at line numbers; it does not supply the citation text. See
`lines.py` for why, and `structured.py` for how the JSON is obtained reliably.

Whatever comes back is only a *claim*. `pipeline.py` decides whether it stands.
"""

from __future__ import annotations

from typing import Sequence

from .models import Correction, ModelAnswer, Turn
from .prompts import ANSWER_SCHEMA, build_messages
from .structured import MalformedOutput, complete_structured


def ask_model(
    numbered_document: str,
    question: str,
    *,
    history: Sequence[Turn] = (),
    corrections: Sequence[Correction] = (),
) -> ModelAnswer:
    """Get the model's answer and the lines it claims support it."""
    data = complete_structured(
        build_messages(
            numbered_document,
            question,
            history=history,
            corrections=corrections,
        ),
        ANSWER_SCHEMA,
    )

    try:
        return ModelAnswer.model_validate(data)
    except Exception as exc:
        # `json_object` mode returns valid JSON that silently omits required
        # fields, so schema validation is doing real work here, not ceremony.
        raise MalformedOutput(f"unexpected answer shape: {data}") from exc
