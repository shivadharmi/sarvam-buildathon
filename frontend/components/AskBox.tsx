"use client";

import { askPlaceholder } from "@/lib/languages";

interface AskBoxProps {
  value: string;
  onChange: (value: string) => void;
  onSubmit: () => void;
  /** The page's language, so the prompt is in the script the reader reads. */
  language?: string | null;
  disabled?: boolean;
  pending?: boolean;
  error?: string | null;
}

/**
 * One box for anything the reader types.
 *
 * A question or a statement — the backend decides which, and its reply says
 * so. Splitting them into two controls would make the reader classify their
 * own sentence before they are allowed to say it.
 */
export function AskBox({
  value,
  onChange,
  onSubmit,
  language,
  disabled,
  pending,
  error,
}: AskBoxProps) {
  return (
    <div className="shrink-0 border-t border-rule px-5 py-4">
      <form
        onSubmit={(event) => {
          event.preventDefault();
          onSubmit();
        }}
      >
        <label htmlFor="question" className="sr-only">
          Ask this page
        </label>
        <div className="flex gap-2">
          <input
            id="question"
            value={value}
            onChange={(event) => onChange(event.target.value)}
            placeholder={askPlaceholder(language)}
            disabled={disabled}
            className="font-indic min-w-0 flex-1 border border-rule bg-surface px-3 py-2 text-sm outline-none placeholder:text-faint focus:border-duplicator disabled:opacity-50"
          />
          <button
            type="submit"
            disabled={disabled || !value.trim()}
            className="shrink-0 bg-duplicator px-4 py-2 text-xs font-medium text-white transition-opacity disabled:opacity-40"
          >
            {pending ? "Checking…" : "Ask"}
          </button>
        </div>
      </form>

      {error && (
        <p
          role="alert"
          className="mt-3 border-l-2 border-seal bg-seal-wash px-3 py-2 text-xs text-seal"
        >
          {error}
        </p>
      )}
    </div>
  );
}
