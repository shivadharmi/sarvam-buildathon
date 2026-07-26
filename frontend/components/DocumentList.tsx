import Link from "next/link";

import { languageName } from "@/lib/languages";
import { fullName } from "@/lib/questions";
import type { DigitisedDoc, LanguageSource } from "@/lib/types";

/**
 * How we came to read a page in the language we did — the same wording the
 * reader page uses, so the two never tell different stories about one document.
 */
const SOURCE_NOTES: Record<LanguageSource, string> = {
  detected: "language worked out from the page",
  script: "language read from the script",
  user: "language you chose",
  builtin: "",
};

interface DocumentListProps {
  documents: DigitisedDoc[];
  /** Highlights a page that was just added. */
  highlightId?: string | null;
}

/**
 * Everything there is to read, builtins first.
 *
 * A list, not a corpus: each row opens one page at its own address, and a
 * question only ever reaches the page it was asked on.
 *
 * The two demo documents are pinned to the top because they are the ones the
 * offline cache covers — the ones that still work when the API does not.
 */
export function DocumentList({ documents, highlightId }: DocumentListProps) {
  // Stable sort, so uploads keep the newest-first order the server sent.
  const ordered = [...documents].sort(
    (a, b) => (a.origin === "upload" ? 1 : 0) - (b.origin === "upload" ? 1 : 0),
  );

  if (ordered.length === 0) {
    return (
      <p className="text-xs leading-relaxed text-muted">
        Nothing to read yet. Add a page above, or run{" "}
        <code className="font-mono text-xs">askdoc.cli digitise --doc doc_a</code> for
        the demo documents.
      </p>
    );
  }

  return (
    <ul className="divide-y divide-rule-soft border-y border-rule-soft">
      {ordered.map((doc) => {
        const note = SOURCE_NOTES[doc.language_source ?? "builtin"] ?? "";
        const lines = doc.text.split("\n").length;

        return (
          <li key={doc.doc_id}>
            <Link
              href={`/doc/${encodeURIComponent(doc.doc_id)}`}
              className={`flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1 px-3 py-3 transition-colors hover:bg-surface ${
                doc.doc_id === highlightId ? "bg-surface" : ""
              }`}
            >
              <span className="text-sm text-ink">{fullName(doc)}</span>
              <span className="text-xs text-faint">
                {languageName(doc.language)}
                {note && ` · ${note}`}
                {" · "}
                {lines} lines
                {doc.page_count > 1 && ` · ${doc.page_count} pages`}
              </span>
            </Link>
          </li>
        );
      })}
    </ul>
  );
}
