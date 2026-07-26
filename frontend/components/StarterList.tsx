"use client";

import type { StarterQuestion } from "@/lib/questions";

interface StarterListProps {
  starters: StarterQuestion[];
  onAsk: (text: string) => void;
  disabled?: boolean;
}

/**
 * What to ask a page you cannot read.
 *
 * The demo documents carry hand-written sets whose refusal and needs-a-note
 * cases were checked by hand; an upload's are generated, and may come back
 * empty. Empty is not an error state — the input box below works either way,
 * and an apology where a suggestion should be would read as a broken page.
 */
export function StarterList({ starters, onAsk, disabled }: StarterListProps) {
  return (
    <div className="px-5 py-5">
      <p className="eyebrow">Ask this page anything</p>
      <p className="mt-2 text-xs leading-relaxed text-muted">
        Follow-ups work — ask &ldquo;and the age limit?&rdquo; after a first answer and
        it knows what you mean.
      </p>

      {starters.length > 0 && (
        <ul className="mt-4 space-y-1">
          {starters.map((starter) => (
            <li key={starter.text}>
              <button
                type="button"
                onClick={() => onAsk(starter.text)}
                disabled={disabled}
                className="w-full px-2 py-1.5 text-left transition-colors hover:bg-surface disabled:opacity-40"
              >
                <span className="font-indic block text-[0.8125rem] leading-snug text-ink">
                  {starter.text}
                </span>
                <span className="mt-0.5 block text-xs text-faint">
                  {starter.gloss}
                  {starter.unanswerable && " — not on this page"}
                  {starter.needsNote && " — needs a note above"}
                </span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
