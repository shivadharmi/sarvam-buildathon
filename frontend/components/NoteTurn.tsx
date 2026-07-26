"use client";

import type { NoteAcknowledgement } from "@/lib/types";

interface NoteTurnProps {
  item: NoteAcknowledgement;
}

/**
 * The reader stated something rather than asking something.
 *
 * Rendered in the pencil register — dashed rule, muted ink — matching the
 * "About you" panel, because this is the same kind of thing: reader-authored
 * context, not a claim about the document. It carries neither the violet of a
 * citation nor the red of a refusal, since it is neither.
 */
export function NoteTurn({ item }: NoteTurnProps) {
  return (
    <li className="px-5 py-4">
      <div className="flex justify-end">
        <div className="max-w-[85%] bg-surface px-3 py-2">
          <p className="font-indic text-right text-[0.875rem] leading-snug text-ink">
            {item.note}
          </p>
        </div>
      </div>

      <div className="mt-2.5 border-l-2 border-dashed border-rule py-1.5 pl-3">
        <p className="font-indic text-[0.875rem] leading-relaxed text-muted">
          {item.acknowledgement}
        </p>
        <p className="eyebrow mt-1.5">Remembered for this chat</p>
      </div>
    </li>
  );
}
