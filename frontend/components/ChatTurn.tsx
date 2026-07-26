"use client";

import type { AnswerRecord, RefusalReason } from "@/lib/types";

/**
 * What the reader is told when an answer does not stand.
 *
 * Only "document_silent" may say the page doesn't say it. The others are
 * limits of ours, and wording them as silence would tell the reader the page
 * lacks something it contains — which is the failure this product exists to
 * prevent. Each gets its own words, and the two that are recoverable say how.
 */
const REFUSALS: Record<RefusalReason, { headline: string; detail: string }> = {
  document_silent: {
    headline: "This page doesn't say.",
    detail: "No line here answers that, so nothing is quoted.",
  },
  not_relevant: {
    headline: "This page doesn't say.",
    detail: "Nothing here answers that question, so nothing is quoted.",
  },
  citation_too_broad: {
    headline: "Too much of the page to quote.",
    detail:
      "The page does cover this, but the answer runs across more of it than can be quoted as one citation. Try asking about one part — a date, a fee, a specific post.",
  },
  citation_invalid: {
    headline: "Couldn't verify a citation.",
    detail:
      "The answer couldn't be pinned to specific lines on this page, so it isn't shown. Try asking again, or more specifically.",
  },
};

const UNKNOWN_REFUSAL = {
  headline: "No answer shown.",
  detail: "This one couldn't be backed by a line on the page.",
};

interface ChatTurnProps {
  record: AnswerRecord;
  gloss?: string;
  isActive: boolean;
  onSelect: () => void;
}

/**
 * One exchange in the thread: the question asked, and the verified reply.
 *
 * Cited and refused replies carry equal visual weight on purpose. A refusal is
 * a result here, not an error -- styling it as a failure would undercut the one
 * thing this product claims to do well.
 */
export function ChatTurn({ record, gloss, isActive, onSelect }: ChatTurnProps) {
  const cited = record.status === "cited";
  const refusal =
    (record.refusal_reason && REFUSALS[record.refusal_reason]) || UNKNOWN_REFUSAL;
  const lineLabel =
    record.quote_from_line === record.quote_to_line
      ? `Line ${record.quote_from_line}`
      : `Lines ${record.quote_from_line}–${record.quote_to_line}`;

  return (
    <li className="px-5 py-4">
      {/* The question, as asked. */}
      <div className="flex justify-end">
        <div className="max-w-[85%] bg-surface px-3 py-2">
          <p className="font-indic text-right text-[0.875rem] leading-snug text-ink">
            {record.question}
          </p>
          {gloss && <p className="mt-0.5 text-right text-xs text-faint">{gloss}</p>}
        </div>
      </div>

      {/* The reply. Clicking it takes the page back to those lines. */}
      <button
        type="button"
        onClick={onSelect}
        aria-pressed={isActive}
        // Active state is neutral on purpose: violet means "from the
        // document" everywhere else, and washing a refusal in it would say
        // the opposite of what happened.
        className={`mt-2.5 w-full border-l-2 py-1.5 pl-3 text-left transition-colors ${
          cited ? "border-duplicator" : "border-seal"
        } ${isActive ? "bg-surface" : "hover:bg-surface/60"}`}
      >
        {cited ? (
          <>
            <p className="font-indic text-[0.875rem] leading-relaxed text-ink">
              {record.answer}
            </p>
            <p className="eyebrow mt-2 text-duplicator">{lineLabel} of this page</p>
          </>
        ) : (
          <>
            <p className="text-[0.875rem] font-medium text-seal">{refusal.headline}</p>
            <p className="mt-1 text-xs leading-relaxed text-faint">{refusal.detail}</p>
          </>
        )}

        {record.model_quote_matched === false && (
          <p className="mt-2 text-xs leading-relaxed text-faint">
            The model&apos;s wording differed from the lines it pointed at. The lines
            are shown as they appear on the page.
          </p>
        )}
      </button>
    </li>
  );
}
