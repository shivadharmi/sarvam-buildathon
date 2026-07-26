"use client";

import { useState } from "react";

import { LANGUAGE_OPTIONS } from "@/lib/languages";

interface LanguagePickerProps {
  /** What we currently believe, preselected so a correction is one change. */
  current?: string | null;
  onChoose: (language: string) => void;
  disabled?: boolean;
  submitLabel?: string;
}

/**
 * Which language this page is in.
 *
 * Answers two questions with one control: the detector declining to guess
 * between languages that share a script, and a reader overruling a guess it
 * did make. Both are the same statement — "this page is in X" — so they get
 * the same control rather than two dialects of one idea.
 *
 * A plain select, not 23 chips: the list is long, alphabetical and boring, and
 * the native control already knows how to be searchable on every platform.
 */
export function LanguagePicker({
  current,
  onChoose,
  disabled,
  submitLabel = "Read it in this",
}: LanguagePickerProps) {
  const [choice, setChoice] = useState(current ?? "");

  return (
    <div className="flex flex-wrap gap-2">
      <label htmlFor="language" className="sr-only">
        Language of this page
      </label>
      <select
        id="language"
        value={choice}
        onChange={(event) => setChoice(event.target.value)}
        disabled={disabled}
        className="min-w-0 flex-1 border border-rule bg-surface px-2.5 py-1.5 text-xs text-ink outline-none focus:border-duplicator disabled:opacity-50"
      >
        <option value="">Choose a language…</option>
        {LANGUAGE_OPTIONS.map((option) => (
          <option key={option.code} value={option.code}>
            {option.name}
          </option>
        ))}
      </select>

      <button
        type="button"
        onClick={() => choice && onChoose(choice)}
        disabled={disabled || !choice || choice === current}
        className="shrink-0 border border-ink px-3 py-1.5 text-xs transition-opacity disabled:opacity-40"
      >
        {submitLabel}
      </button>
    </div>
  );
}
