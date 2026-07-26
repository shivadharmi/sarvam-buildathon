"""The faithfulness gate -- the core invariant of this product.

An answer is only allowed to stand if the model's supporting quote is
*literally present* in the digitised text. The model's own `found` flag is
never trusted; this deterministic check is the gate.

Three normalisations are applied before comparing, and no others:

1. **NFC** -- canonical Unicode composition. Tamil and Telugu can encode the
   same visible text as different codepoint sequences, so without this a
   genuinely verbatim quote could be wrongly refused.
2. **Whitespace collapsing** -- the model re-wraps lines; the source has
   layout.
3. **Case folding** -- for the English fragments mixed into these pages.

All three preserve identity of the underlying characters. Anything beyond them
(stemming, edit distance, embeddings, token overlap) would turn this into a
fuzzy match and destroy the guarantee. Do not add a fourth.
"""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass


@dataclass(frozen=True)
class GateResult:
    """Outcome of checking one quote against one source text.

    On success, `source[start:end]` is the verbatim span -- offsets are into
    the NFC-normalised source, which is what the pipeline stores and renders.
    """

    passed: bool
    start: int | None = None
    end: int | None = None
    matched_text: str | None = None


def _fold(text: str) -> tuple[str, list[int]]:
    """Collapse whitespace and lowercase, tracking where each character came from.

    Returns the folded string plus `origin`, where `origin[i]` is the index in
    `text` of the character that produced folded character `i`. The map is what
    lets a match found in folded space be reported as offsets in the real text,
    so the UI can highlight the span exactly as it appears on the page.
    """
    folded: list[str] = []
    origin: list[int] = []
    pending_space = False

    for index, char in enumerate(text):
        if char.isspace():
            # Only becomes a separator if real content precedes it, which
            # discards leading whitespace; trailing whitespace is never
            # flushed, which discards it too.
            pending_space = bool(folded)
            continue

        if pending_space:
            folded.append(" ")
            origin.append(index)
            pending_space = False

        # lower() can expand one character into several, so map each result
        # character back to the same source index rather than assuming 1:1.
        for lowered in char.lower():
            folded.append(lowered)
            origin.append(index)

    return "".join(folded), origin


def check_quote(quote: str, source: str) -> GateResult:
    """Return whether `quote` appears verbatim in `source`, and where.

    This is a pure function with no network or model involvement -- that is
    precisely why it can be trusted to overrule the model.
    """
    canonical = unicodedata.normalize("NFC", source)

    folded_source, origin = _fold(canonical)
    folded_quote, _ = _fold(unicodedata.normalize("NFC", quote))

    if not folded_quote or not folded_source:
        return GateResult(passed=False)

    position = folded_source.find(folded_quote)
    if position == -1:
        return GateResult(passed=False)

    start = origin[position]
    end = origin[position + len(folded_quote) - 1] + 1

    return GateResult(
        passed=True,
        start=start,
        end=end,
        matched_text=canonical[start:end],
    )
