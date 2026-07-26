"""Run the labelled cases and report where we stand.

    python -m askdoc.evaluate            # one pass
    python -m askdoc.evaluate --runs 3   # M5 stability check

Three outcomes are tracked separately, because they fail for different reasons
and need different fixes:

* **correct**       -- cited the right passage, or refused when it should have
* **irrelevant**    -- cited genuine verbatim text that answers something else
* **false refusal** -- refused a question the document does answer

Only the first is success. Conflating "irrelevant" with "wrong" would hide the
fact that the citation machinery worked perfectly and retrieval is what failed.
"""

from __future__ import annotations

import argparse
from collections import Counter

from . import cache
from .evalset import CASES, Case
from .models import AnswerRecord, AnswerStatus
from .pipeline import ask

GREEN, RED, YELLOW, DIM, BOLD, RESET = (
    "\033[32m", "\033[31m", "\033[33m", "\033[2m", "\033[1m", "\033[0m"
)

CORRECT, IRRELEVANT, FALSE_REFUSAL, WRONG_ANSWER, ERROR = (
    "correct", "irrelevant", "false refusal", "should have refused", "error"
)


def classify(case: Case, record: AnswerRecord) -> str:
    """Score one answer against ground truth."""
    if case.expect is AnswerStatus.NOT_STATED:
        return CORRECT if record.status is AnswerStatus.NOT_STATED else WRONG_ANSWER

    if record.status is AnswerStatus.NOT_STATED:
        return FALSE_REFUSAL

    if case.must_contain and case.must_contain not in (record.quote or ""):
        return IRRELEVANT

    return CORRECT


def _colour(outcome: str) -> str:
    if outcome == CORRECT:
        return GREEN
    return YELLOW if outcome == IRRELEVANT else RED


def run(runs: int = 1, doc_filter: str | None = None) -> Counter:
    cases = [c for c in CASES if not doc_filter or c.doc_id == doc_filter]
    docs = {c.doc_id: cache.load(c.doc_id) for c in cases}

    missing = [d for d, doc in docs.items() if doc is None]
    if missing:
        raise SystemExit(f"Not digitised yet: {missing}. Run: askdoc.cli digitise --doc {missing[0]}")

    tally: Counter = Counter()

    for attempt in range(1, runs + 1):
        if runs > 1:
            print(f"\n{BOLD}=== run {attempt}/{runs} ==={RESET}")

        for case in cases:
            try:
                record = ask(docs[case.doc_id], case.question)
                outcome = classify(case, record)
            except Exception as exc:  # noqa: BLE001 -- an error is a result here
                outcome, record = ERROR, None
                detail = f"{type(exc).__name__}: {exc}"

            tally[outcome] += 1
            mark = "✓" if outcome == CORRECT else "✗"
            print(f"{_colour(outcome)}{mark} {outcome:20}{RESET} "
                  f"[{case.doc_id}] {case.label}")

            if outcome == IRRELEVANT:
                print(f"{DIM}    wanted: {case.must_contain}{RESET}")
                print(f"{DIM}    cited : {(record.quote or '')[:90]}{RESET}")
            elif outcome == FALSE_REFUSAL:
                print(f"{DIM}    reason: {record.rejection_reason}{RESET}")
            elif outcome == WRONG_ANSWER:
                print(f"{DIM}    cited : {(record.quote or '')[:90]}{RESET}")
            elif outcome == ERROR:
                print(f"{DIM}    {detail}{RESET}")

    total = sum(tally.values())
    correct = tally[CORRECT]
    print(f"\n{BOLD}{correct}/{total} correct ({100 * correct / total:.0f}%){RESET}")
    for outcome, count in tally.most_common():
        if outcome != CORRECT:
            print(f"  {_colour(outcome)}{count} {outcome}{RESET}")
    return tally


def main() -> None:
    parser = argparse.ArgumentParser(prog="askdoc.evaluate")
    parser.add_argument("--runs", type=int, default=1)
    parser.add_argument("--doc", default=None, help="limit to one document")
    args = parser.parse_args()
    run(runs=args.runs, doc_filter=args.doc)


if __name__ == "__main__":
    main()
