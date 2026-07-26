"""Line-anchored citation.

The model is shown the document with numbered lines and returns a line *range*
rather than the quote text. We then slice that range out of our own copy.

This is a strengthening of the faithfulness gate, not a relaxation of it.
Under the previous design the model retyped the quote and we checked it, which
meant a correct answer could be thrown away over a one-character slip -- and in
practice it was, on about a third of answerable questions. Here the model never
types the quote at all, so paraphrase is structurally impossible rather than
detected after the fact.

What still gets verified, deterministically:

* the range is within the document
* it is not inverted or empty
* it is short enough to be actual evidence (see MAX_QUOTE_LINES)

And `gate.check_quote` is still used, on the model's optional self-reported
quote, purely to surface when it cited something other than what it pointed at.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

# A citation must be a *part* of the page, not the page. Without a cap the
# model could point at every line, satisfy every check, and prove nothing.
#
# The cap is proportional rather than fixed. A flat 8 lines was a crude proxy
# for "part, not whole": it refused a legitimate 15-line answer to "help me
# understand this notification" -- which is probably the most common thing a
# real reader asks of a dense official page. A quarter of the page is still
# unmistakably a part of it, while "cite everything" remains impossible.
MIN_QUOTE_LINES = 8
MAX_QUOTE_LINES = 30
QUOTE_SHARE = 0.25

SEPARATOR = " | "


def max_quote_lines(total_lines: int) -> int:
    """How many lines a single citation may span for a document this long."""
    proportional = math.ceil(total_lines * QUOTE_SHARE)
    return max(MIN_QUOTE_LINES, min(MAX_QUOTE_LINES, proportional))


@dataclass(frozen=True)
class LineSpan:
    """A resolved line range, or the reason it could not be used."""

    valid: bool
    start: int | None = None
    end: int | None = None
    text: str | None = None
    reason: str | None = None
    #: True when the range was refused because it was wider than we allow --
    #: a limit of ours, NOT the document being silent. The two must never be
    #: reported to the reader as the same thing.
    too_broad: bool = False


def _line_bounds(text: str) -> list[tuple[int, int]]:
    """Character offsets (start, end) of each line, excluding its newline."""
    bounds: list[tuple[int, int]] = []
    cursor = 0
    for line in text.split("\n"):
        bounds.append((cursor, cursor + len(line)))
        cursor += len(line) + 1  # +1 for the newline we split on
    return bounds


def render_numbered(text: str) -> str:
    """Render the document with 1-based line numbers, for the prompt.

    The numbering here and the indexing in `extract_lines` are the same
    contract; `test_lines.py` pins them together.
    """
    lines = text.split("\n")
    width = len(str(len(lines)))
    return "\n".join(
        f"{index:>{width}}{SEPARATOR}{line}"
        for index, line in enumerate(lines, start=1)
    )


def extract_lines(text: str, from_line: int, to_line: int) -> LineSpan:
    """Slice lines `from_line`..`to_line` (inclusive, 1-based) out of `text`."""
    bounds = _line_bounds(text)
    total = len(bounds)

    if from_line < 1 or to_line < 1:
        return LineSpan(False, reason=f"line numbers start at 1, got {from_line}-{to_line}")
    if to_line < from_line:
        return LineSpan(False, reason=f"inverted range {from_line}-{to_line}")
    if from_line > total or to_line > total:
        return LineSpan(False, reason=f"range {from_line}-{to_line} exceeds {total} lines")

    allowed = max_quote_lines(total)
    if to_line - from_line + 1 > allowed:
        return LineSpan(
            False,
            reason=(
                f"range {from_line}-{to_line} spans "
                f"{to_line - from_line + 1} lines; at most {allowed} may be cited "
                f"from a {total}-line document"
            ),
            too_broad=True,
        )

    start = bounds[from_line - 1][0]
    end = bounds[to_line - 1][1]
    span = text[start:end]

    if not span.strip():
        return LineSpan(False, reason=f"lines {from_line}-{to_line} are blank")

    return LineSpan(True, start=start, end=end, text=span)
