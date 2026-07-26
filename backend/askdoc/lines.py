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

Width is **measured and reported, never refused**. A wide citation was once
rejected outright, on the reasoning that citing everything proves nothing.
That reasoning is sound about *evidence* and wrong about *what to do*: breadth
makes a citation weaker, not false, and refusing threw away a correct, fully
verified answer to prevent a merely unimpressive one. It is the same mistake
as the substring gate and the relevance judge, both reverted for the same
reason -- a check that destroys correct answers costs more than it saves.

The reader is told how much of the page a citation covers and decides for
themselves. See `broad_above`.

And `gate.check_quote` is still used, on the model's optional self-reported
quote, purely to surface when it cited something other than what it pointed at.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

# How wide a citation gets before it is worth telling the reader it is wide.
#
# ⚠️ This is a LABEL, not a limit. It used to be a cap that refused the answer,
# and refusing was the wrong response to it -- see `broad` below.
BROAD_MIN_LINES = 8
BROAD_MAX_LINES = 30
BROAD_SHARE = 0.25

SEPARATOR = " | "


def broad_above(total_lines: int) -> int:
    """Beyond this many lines, a citation is a large part of a page this long."""
    proportional = math.ceil(total_lines * BROAD_SHARE)
    return max(BROAD_MIN_LINES, min(BROAD_MAX_LINES, proportional))


@dataclass(frozen=True)
class LineSpan:
    """A resolved line range, or the reason it could not be used."""

    valid: bool
    start: int | None = None
    end: int | None = None
    text: str | None = None
    reason: str | None = None
    #: How many lines the citation covers, and whether that is a large part of
    #: this page. Shown to the reader, never used to refuse them -- breadth
    #: makes a citation weaker evidence, not false evidence.
    line_count: int = 0
    broad: bool = False


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

    start = bounds[from_line - 1][0]
    end = bounds[to_line - 1][1]
    span = text[start:end]

    if not span.strip():
        return LineSpan(False, reason=f"lines {from_line}-{to_line} are blank")

    count = to_line - from_line + 1
    return LineSpan(
        True,
        start=start,
        end=end,
        text=span,
        line_count=count,
        broad=count > broad_above(total),
    )
