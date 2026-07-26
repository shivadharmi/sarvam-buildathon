"use client";

import { LanguagePicker } from "@/components/LanguagePicker";
import { UploadDropzone } from "@/components/UploadDropzone";
import type { IngestionJob } from "@/lib/useIngestionJob";

interface IngestionPanelProps {
  ingestion: IngestionJob;
}

/**
 * Taking in a page of the reader's own — the dropzone and everything that
 * happens to what lands in it.
 *
 * It lives on the library, and so does every answer about the file: the
 * stages, a rejection, a language we could not work out, a failure. Nothing
 * navigates to a reader until there is a document to read, so a failed job
 * never strands anyone on a page with nothing on it.
 *
 * It narrates the passes rather than spinning: the file is read once to find
 * out what language it is in, then read again in that language, and a reader
 * who is told that can tell a slow job from a stuck one — and can catch a
 * wrong language before it garbles the whole page.
 */
export function IngestionPanel({ ingestion }: IngestionPanelProps) {
  const { busy, error, message, needsLanguage, pendingDocId, job } = ingestion;

  // Once a language question is open, the file is settled — offering the
  // dropzone again would invite the reader to answer a different question.
  const showDropzone = pendingDocId === null;

  // A rejection is about the file, and belongs against the box that took it.
  // Anything later is about the page, and is reported on its own.
  const rejection = showDropzone && !job ? error : null;
  const failure = error && !rejection ? error : null;

  return (
    <div className="max-w-[34rem]">
      <div>
        {showDropzone && (
          <UploadDropzone onFile={ingestion.upload} disabled={busy} error={rejection} />
        )}

        {message && (
          <p className="mt-2 text-xs text-muted" aria-live="polite">
            {message}
          </p>
        )}

        {needsLanguage && pendingDocId && (
          <div className="border border-dashed border-rule px-3 py-3">
            <p className="text-xs font-medium text-ink">Which language is this page in?</p>
            <p className="mt-1 mb-2.5 text-xs leading-relaxed text-muted">
              Its script is shared by several languages
              {job?.script ? ` (${job.script})` : ""}, and guessing wrong would garble
              the reading. So we are asking instead of guessing.
            </p>
            <LanguagePicker
              onChoose={(language) => ingestion.chooseLanguage(pendingDocId, language)}
              disabled={busy}
            />
          </div>
        )}

        {failure && (
          <p
            role="alert"
            className="mt-2 border-l-2 border-seal bg-seal-wash px-3 py-2 text-xs leading-relaxed text-seal"
          >
            {failure}
          </p>
        )}
      </div>
    </div>
  );
}
