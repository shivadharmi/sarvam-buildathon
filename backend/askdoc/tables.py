"""Collapse digitised HTML tables into one citable line per row.

Sarvam returns tables as HTML with one cell per line. That splits a table row
-- the unit that actually carries meaning -- across half a dozen lines, so a
line-anchored citation can land on `<td>09</td>`: perfectly verbatim, and
useless, because nothing on that line says what the 09 counts.

Rewriting each row as a single pipe-delimited line fixes the evidence problem
at its source. A citation then reads `| 1 | గద్వాల్ | 28 | 05 | 33 |`, which
stands on its own.

This runs once at ingestion, before any offset or line number is computed, so
everything downstream stays consistent. It is a content-preserving
normalisation of our own canonical text -- the same category as NFC -- and it
does not touch the invariant: the model still cannot author a citation.
"""

from __future__ import annotations

import re

TABLE = re.compile(r"<table\b.*?(?:</table>|$)", re.IGNORECASE | re.DOTALL)
ROW = re.compile(r"<tr\b[^>]*>(.*?)(?:</tr>|(?=<tr\b)|$)", re.IGNORECASE | re.DOTALL)
CELL = re.compile(r"<(t[hd])\b[^>]*>(.*?)(?:</\1>|(?=<t[hd]\b)|$)", re.IGNORECASE | re.DOTALL)
TAG = re.compile(r"<[^>]*>")


def _cell_text(raw: str) -> str:
    """Strip any inner markup and normalise whitespace to a single line."""
    return " ".join(TAG.sub("", raw).split())


def _flatten_row(row_html: str) -> str | None:
    cells = [_cell_text(body) for _, body in CELL.findall(row_html)]
    if not cells:
        return None
    return "| " + " | ".join(cells) + " |"


def _flatten_table(match: re.Match[str]) -> str:
    rows = [_flatten_row(row) for row in ROW.findall(match.group(0))]
    kept = [row for row in rows if row]

    if not kept:
        # Nothing parseable -- return the text without tags rather than
        # silently dropping content we failed to understand.
        return _cell_text(match.group(0))

    return "\n".join(kept)


def flatten_tables(text: str) -> str:
    """Rewrite every HTML table so each row occupies exactly one line."""
    if "<table" not in text.lower():
        return text
    return TABLE.sub(_flatten_table, text)
