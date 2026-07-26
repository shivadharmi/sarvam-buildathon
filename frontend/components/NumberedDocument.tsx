"use client";

import { useEffect, useRef } from "react";

interface NumberedDocumentProps {
  text: string;
  /** 1-based, inclusive. Null when nothing is cited. */
  citedFrom: number | null;
  citedTo: number | null;
}

const MARKUP_SPLIT = /(<\/?[a-zA-Z][^>]*>)/g;
// Separate, non-global copy: `.test()` on a /g regex advances lastIndex and
// would return alternating results for the same input.
const IS_MARKUP = /^<\/?[a-zA-Z][^>]*>$/;

/**
 * Split a line into markup tags and readable content.
 *
 * The digitiser emits HTML for tables, and those tags stay in the document
 * text on purpose: they carry the table's structure for the model, and
 * removing them would shift every line number and break the citation anchor.
 * So they are dimmed here rather than stripped -- nothing is hidden, it just
 * stops competing with the content.
 */
function segments(line: string): { text: string; isMarkup: boolean }[] {
  return line
    .split(MARKUP_SPLIT)
    .filter(Boolean)
    .map((part) => ({ text: part, isMarkup: IS_MARKUP.test(part) }));
}

/**
 * The document, rendered exactly as the model sees it: one numbered line each.
 *
 * The numbers are not ornament. They are the citation mechanism itself -- the
 * model answers by pointing at a line range, and the quoted text is then
 * sliced out of this same string. Showing them lets a reader check the
 * machinery instead of trusting it.
 */
export function NumberedDocument({ text, citedFrom, citedTo }: NumberedDocumentProps) {
  const lines = text.split("\n");
  const gutter = String(lines.length).length;
  const firstCitedRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    firstCitedRef.current?.scrollIntoView({ block: "center", behavior: "smooth" });
  }, [citedFrom, citedTo]);

  return (
    // Capped measure: these are long Tamil and Telugu sentences, and letting
    // them run the full width of a desktop makes the page unreadable.
    <div className="font-indic max-w-[62rem] text-[0.9375rem] leading-[1.9]">
      {lines.map((line, index) => {
        const number = index + 1;
        const isCited =
          citedFrom !== null && citedTo !== null && number >= citedFrom && number <= citedTo;
        const isFirstCited = isCited && number === citedFrom;

        return (
          <div
            key={number}
            ref={isFirstCited ? firstCitedRef : undefined}
            className={`flex gap-4 pr-3 ${isCited ? "cited-line" : ""} ${
              isFirstCited ? "cited-line-first" : ""
            }`}
          >
            <span
              aria-hidden
              className={`shrink-0 select-none pl-3 text-right font-mono text-[0.6875rem] leading-[1.9] tabular-nums ${
                isCited ? "text-duplicator" : "text-faint/70"
              }`}
              style={{ width: `${gutter + 1}ch` }}
            >
              {number}
            </span>
            <span className={isCited ? "text-ink" : "text-ink/85"}>
              {line ? (
                segments(line).map((segment, position) =>
                  segment.isMarkup ? (
                    <span key={position} className="font-mono text-[0.75em] text-faint/50">
                      {segment.text}
                    </span>
                  ) : (
                    <span key={position}>{segment.text}</span>
                  ),
                )
              ) : (
                " "
              )}
            </span>
          </div>
        );
      })}
    </div>
  );
}
