"use client";

import { useState } from "react";

import type { StarterNote } from "@/lib/questions";
import type { Correction } from "@/lib/types";

interface ReaderNotesProps {
  notes: Correction[];
  suggestions?: StarterNote[];
  onAdd: (note: string) => void;
  onRemove: (index: number) => void;
  disabled?: boolean;
}

/**
 * Things the reader has told the page about their own situation.
 *
 * Styled as pencil annotation -- dashed rules, muted ink -- because the
 * palette encodes provenance elsewhere: violet means "from the document", red
 * means "the document is silent". A note is neither, and giving it either
 * colour would misstate where it came from.
 *
 * These carry into every later question in the conversation. They change which
 * lines get cited; they never become a citation.
 */
export function ReaderNotes({
  notes,
  suggestions = [],
  onAdd,
  onRemove,
  disabled,
}: ReaderNotesProps) {
  const [draft, setDraft] = useState("");
  const [open, setOpen] = useState(false);

  const add = (text: string) => {
    const trimmed = text.trim();
    if (!trimmed) return;
    onAdd(trimmed);
    setDraft("");
  };

  const unused = suggestions.filter(
    (suggestion) => !notes.some((note) => note.note === suggestion.note),
  );

  return (
    <div>
      <div className="flex items-baseline justify-between gap-2">
        <p className="eyebrow">About you {notes.length > 0 && `· ${notes.length}`}</p>
        <button
          type="button"
          onClick={() => setOpen((current) => !current)}
          className="text-xs text-muted underline-offset-2 hover:text-ink hover:underline"
        >
          {open ? "Done" : "Add"}
        </button>
      </div>

      {notes.length > 0 && (
        <ul className="mt-2 space-y-1.5">
          {notes.map((note, index) => (
            <li
              key={`${note.note}-${index}`}
              className="flex items-start gap-2 border border-dashed border-rule px-2.5 py-1.5"
            >
              <span className="font-indic flex-1 text-xs leading-relaxed text-muted">
                {note.note}
              </span>
              <button
                type="button"
                onClick={() => onRemove(index)}
                aria-label={`Remove: ${note.note}`}
                className="shrink-0 text-xs text-faint hover:text-seal"
              >
                ✕
              </button>
            </li>
          ))}
        </ul>
      )}

      {/* One click to the thing the page cannot work out on its own. */}
      {!open && notes.length === 0 && unused.length > 0 && (
        <ul className="mt-2 space-y-1">
          {unused.map((suggestion) => (
            <li key={suggestion.note}>
              <button
                type="button"
                onClick={() => add(suggestion.note)}
                disabled={disabled}
                className="w-full border border-dashed border-rule px-2.5 py-1.5 text-left transition-colors hover:border-ink disabled:opacity-40"
              >
                <span className="font-indic block text-xs leading-snug text-muted">
                  {suggestion.note}
                </span>
                <span className="mt-0.5 block text-xs text-faint">
                  {suggestion.gloss}
                </span>
              </button>
            </li>
          ))}
        </ul>
      )}

      {open && (
        <div className="mt-2">
          <div className="flex gap-2">
            <input
              value={draft}
              onChange={(event) => setDraft(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Enter") {
                  event.preventDefault();
                  add(draft);
                }
              }}
              placeholder="e.g. I'm applying to the Maldakal project"
              disabled={disabled}
              maxLength={300}
              className="font-indic min-w-0 flex-1 border border-dashed border-rule bg-transparent px-2.5 py-1.5 text-xs outline-none placeholder:text-faint focus:border-ink disabled:opacity-50"
            />
            <button
              type="button"
              onClick={() => add(draft)}
              disabled={disabled || !draft.trim()}
              className="shrink-0 border border-ink px-3 py-1.5 text-xs transition-opacity disabled:opacity-40"
            >
              Save
            </button>
          </div>
          <p className="mt-1.5 text-xs leading-relaxed text-faint">
            Tell it which post or project is yours. It carries into every later
            question — and is never quoted as an answer.
          </p>
        </div>
      )}
    </div>
  );
}
