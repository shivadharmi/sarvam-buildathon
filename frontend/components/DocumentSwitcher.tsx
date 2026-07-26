"use client";

import { fullName, shortLabel } from "@/lib/questions";
import type { DigitisedDoc } from "@/lib/types";

interface DocumentSwitcherProps {
  documents: DigitisedDoc[];
  activeDocId: string | null;
  onSwitch: (docId: string) => void;
  onToggleUpload: () => void;
  uploadOpen: boolean;
}

/**
 * Which page you are asking about.
 *
 * A switcher, not a corpus: exactly one document is live at a time, and
 * choosing another starts a new conversation rather than widening the current
 * one. No question ever reaches across two pages.
 *
 * The two demo pages are pinned first. They are the ones the offline cache
 * covers, so they are the ones that still work when the API does not.
 */
export function DocumentSwitcher({
  documents,
  activeDocId,
  onSwitch,
  onToggleUpload,
  uploadOpen,
}: DocumentSwitcherProps) {
  // Stable sort, so uploads keep the newest-first order the server sent.
  const ordered = [...documents].sort(
    (a, b) => (a.origin === "upload" ? 1 : 0) - (b.origin === "upload" ? 1 : 0),
  );

  return (
    <nav className="ml-auto flex flex-wrap items-center gap-1" aria-label="Choose a document">
      {ordered.map((doc) => {
        const isActive = doc.doc_id === activeDocId;
        return (
          <button
            key={doc.doc_id}
            type="button"
            onClick={() => onSwitch(doc.doc_id)}
            aria-current={isActive ? "page" : undefined}
            title={fullName(doc)}
            className={`px-3 py-1.5 text-xs transition-colors ${
              isActive ? "bg-ink text-paper" : "text-muted hover:bg-surface hover:text-ink"
            }`}
          >
            {shortLabel(doc)}
          </button>
        );
      })}

      <button
        type="button"
        onClick={onToggleUpload}
        aria-expanded={uploadOpen}
        className={`border border-dashed px-3 py-1.5 text-xs transition-colors ${
          uploadOpen
            ? "border-ink text-ink"
            : "border-rule text-muted hover:border-ink hover:text-ink"
        }`}
      >
        {uploadOpen ? "Close" : "+ Add a page"}
      </button>
    </nav>
  );
}
