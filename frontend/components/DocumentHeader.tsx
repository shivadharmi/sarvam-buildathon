"use client";

import { useState } from "react";

import { LanguagePicker } from "@/components/LanguagePicker";
import { languageName } from "@/lib/languages";
import { fullName } from "@/lib/questions";
import type { DigitisedDoc, LanguageSource } from "@/lib/types";

/**
 * How we came to read the page in this language, said plainly.
 *
 * The split is the same honesty beat as a refusal reason. "Detected" and
 * "script" are our claims and can be wrong, so they carry a way to correct
 * them. "You chose this" and a builtin demo page are not guesses, so they do
 * not — offering to fix something nobody guessed at only suggests we did.
 */
const SOURCES: Record<LanguageSource, { note: string; correctable: boolean }> = {
  detected: { note: "worked out from the page", correctable: true },
  script: { note: "read from the script", correctable: true },
  user: { note: "you chose this", correctable: false },
  builtin: { note: "", correctable: false },
};

interface DocumentHeaderProps {
  doc: DigitisedDoc | null;
  onChooseLanguage: (docId: string, language: string) => void;
  busy?: boolean;
  /** Progress while the page is being read again. */
  status?: string | null;
  /** Why a re-read did not happen, in the server's words. */
  error?: string | null;
}

export function DocumentHeader({
  doc,
  onChooseLanguage,
  busy,
  status,
  error,
}: DocumentHeaderProps) {
  const [correcting, setCorrecting] = useState(false);

  if (!doc) {
    return (
      <div className="shrink-0 border-b border-rule px-6 py-3">
        <p className="eyebrow">No document</p>
      </div>
    );
  }

  const source = SOURCES[doc.language_source ?? "builtin"] ?? SOURCES.builtin;
  const lines = doc.text.split("\n").length;

  return (
    <div className="shrink-0 border-b border-rule px-6 py-3">
      <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
        <p className="eyebrow">{fullName(doc)}</p>

        <p className="flex items-baseline gap-2 text-xs text-faint">
          <span>
            {languageName(doc.language)}
            {source.note && ` · ${source.note}`}
            {" · "}
            digitised from a scan · {lines} lines
          </span>

          {source.correctable && (
            <button
              type="button"
              onClick={() => setCorrecting((open) => !open)}
              aria-expanded={correcting}
              className="shrink-0 underline underline-offset-2 hover:text-ink"
            >
              {correcting ? "Cancel" : "Wrong language?"}
            </button>
          )}
        </p>
      </div>

      {correcting && (
        <div className="mt-2.5 max-w-[26rem]">
          <LanguagePicker
            current={doc.language}
            onChoose={(language) => {
              setCorrecting(false);
              onChooseLanguage(doc.doc_id, language);
            }}
            disabled={busy}
            submitLabel="Read it again"
          />
          <p className="mt-1.5 text-xs leading-relaxed text-faint">
            The page is read again from the scan, so this chat starts over — the
            new reading has its own line numbers.
          </p>
        </div>
      )}

      {status && (
        <p className="mt-2 text-xs text-muted" aria-live="polite">
          {status}
        </p>
      )}

      {error && (
        <p
          role="alert"
          className="mt-2 border-l-2 border-seal bg-seal-wash px-3 py-2 text-xs leading-relaxed text-seal"
        >
          {error}
        </p>
      )}
    </div>
  );
}
