"""Console slice: digitise a page, ask questions, print verified answers.

This is the M1 gate. Until this prints a correct answer whose quote genuinely
appears in the digitised text, no UI gets built.

    python -m askdoc.cli digitise --doc doc_a
    python -m askdoc.cli ask --doc doc_a "இந்த வினாத்தொகுப்பில் எத்தனை வினாக்கள் உள்ளன?"
    python -m askdoc.cli show --doc doc_a
"""

from __future__ import annotations

import argparse
import sys
import textwrap

from . import cache
from .config import DOCS_DIR, LANGUAGES
from .digitise import digitise
from .models import AnswerStatus
from .pipeline import ask

# The two demo documents. Both are pure scans with no text layer, so the
# digitised text can only come from Sarvam Vision.
DOCUMENTS = {
    "doc_a": {
        "file": "doc_a_page.png",
        "language": LANGUAGES["ta"],
        "label": "TNPSC Group IV 2024 question booklet cover (Tamil)",
    },
    "doc_b": {
        "file": "doc_b_telugu_anganwadi_jogulamba_notif_only.pdf",
        "language": LANGUAGES["te"],
        "label": "Telangana Anganwadi recruitment notification (Telugu)",
    },
}

GREEN, RED, DIM, BOLD, RESET = "\033[32m", "\033[31m", "\033[2m", "\033[1m", "\033[0m"


def _load(doc_id: str, *, force: bool = False):
    spec = DOCUMENTS.get(doc_id)
    if spec is None:
        sys.exit(f"Unknown doc {doc_id!r}. Known: {', '.join(DOCUMENTS)}")
    return digitise(
        DOCS_DIR / spec["file"],
        language=spec["language"],
        doc_id=doc_id,
        force=force,
    )


def _print_record(record, doc) -> None:
    print(f"\n{BOLD}Q:{RESET} {record.question}")

    if record.status is AnswerStatus.CITED:
        print(f"{GREEN}{BOLD}✓ CITED{RESET}  {record.answer}")
        print(f"{DIM}  lines {record.quote_from_line}–{record.quote_to_line} "
              f"(chars {record.quote_start}–{record.quote_end}):{RESET}")
        for line in textwrap.wrap(record.quote, width=90):
            print(f"{GREEN}  │ {line}{RESET}")
        if record.model_quote_matched is False:
            print(f"{DIM}  note: the model quoted something other than the lines "
                  f"it pointed at; the extracted lines are shown above.{RESET}")
        # Prove the offsets really index the stored text.
        assert doc.text[record.quote_start : record.quote_end] == record.quote
    else:
        print(f"{RED}{BOLD}✗ NOT STATED{RESET}  {record.answer}")
        print(f"{DIM}  reason: {record.rejection_reason}{RESET}")
        if record.model_claimed_found:
            print(f"{DIM}  the model claimed a source; verification rejected it:{RESET}")
            for line in textwrap.wrap(record.model_claimed_quote or "", width=90):
                print(f"{RED}  │ {line}{RESET}")


def main() -> None:
    parser = argparse.ArgumentParser(prog="askdoc")
    sub = parser.add_subparsers(dest="command", required=True)

    p_dig = sub.add_parser("digitise", help="digitise a document and cache it")
    p_dig.add_argument("--doc", default="doc_a")
    p_dig.add_argument("--force", action="store_true", help="re-run the paid API call")

    p_ask = sub.add_parser("ask", help="ask a question")
    p_ask.add_argument("--doc", default="doc_a")
    p_ask.add_argument("questions", nargs="+")

    p_show = sub.add_parser("show", help="print the cached digitised text")
    p_show.add_argument("--doc", default="doc_a")

    args = parser.parse_args()

    if args.command == "digitise":
        doc = _load(args.doc, force=args.force)
        print(f"{GREEN}✓{RESET} {doc.doc_id}: {len(doc.text)} chars, "
              f"{doc.page_count} page(s), {doc.language}")
        print(f"{DIM}cached at {cache._path_for(doc.doc_id)}{RESET}")
        return

    if args.command == "show":
        print(_load(args.doc).text)
        return

    doc = _load(args.doc)
    for question in args.questions:
        _print_record(ask(doc, question), doc)


if __name__ == "__main__":
    main()
