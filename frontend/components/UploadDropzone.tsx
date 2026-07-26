"use client";

import { useRef, useState } from "react";

// The same ceiling the server enforces (askdoc/config.py::MAX_UPLOAD_BYTES).
// Duplicated on purpose: this copy buys instant feedback, the server's copy is
// the guarantee. If they ever disagree the server wins and its message is what
// the reader sees.
const MAX_UPLOAD_BYTES = 25 * 1024 * 1024;
const MAX_UPLOAD_LABEL = "25 MB";

const ACCEPT_ATTRIBUTE = ".pdf,.png,.jpg,.jpeg,application/pdf,image/png,image/jpeg";
const ACCEPTED_TYPES = ["application/pdf", "image/png", "image/jpeg", "image/jpg"];
const ACCEPTED_EXTENSIONS = /\.(pdf|png|jpe?g)$/i;

const WRONG_KIND =
  "I can read PDF, PNG and JPEG pages. This file looks like something else.";

function megabytes(bytes: number): string {
  const mb = bytes / (1024 * 1024);
  return `${mb >= 10 ? Math.round(mb) : mb.toFixed(1)} MB`;
}

/**
 * The courtesy check.
 *
 * A file is rejected here only when both the reported type and the extension
 * say it is not one of ours — browsers report an empty type often enough that
 * trusting either alone would block a file the server would have accepted.
 * Page count is deliberately absent: it needs the PDF parsed, and the server
 * already does that properly.
 */
function precheck(file: File): string | null {
  if (file.size === 0) return "That file is empty.";
  if (file.size > MAX_UPLOAD_BYTES) {
    return `That file is ${megabytes(file.size)}. I can take up to ${MAX_UPLOAD_LABEL}.`;
  }

  const typeSaysYes = ACCEPTED_TYPES.includes(file.type.toLowerCase());
  const nameSaysYes = ACCEPTED_EXTENSIONS.test(file.name);
  if (!typeSaysYes && !nameSaysYes) return WRONG_KIND;

  return null;
}

interface UploadDropzoneProps {
  onFile: (file: File) => void;
  disabled?: boolean;
  /** The server's rejection, shown in its own words. Outranks our own check. */
  error?: string | null;
}

/**
 * Where a reader hands over a page of their own.
 *
 * Dashed rules, as in the notes panel: the palette encodes provenance, and
 * dashed means "the reader brought this", which is exactly what an upload is.
 */
export function UploadDropzone({ onFile, disabled, error }: UploadDropzoneProps) {
  const [over, setOver] = useState(false);
  const [rejection, setRejection] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const offer = (file: File | undefined) => {
    if (!file || disabled) return;
    const problem = precheck(file);
    setRejection(problem);
    if (!problem) onFile(file);
  };

  // The server's word is the one that counts, so it is shown when both exist.
  const problem = error ?? rejection;

  return (
    <div>
      <div
        onDragOver={(event) => {
          event.preventDefault();
          if (!disabled) setOver(true);
        }}
        onDragLeave={() => setOver(false)}
        onDrop={(event) => {
          event.preventDefault();
          setOver(false);
          offer(event.dataTransfer.files[0]);
        }}
        className={`border border-dashed px-4 py-5 text-center transition-colors ${
          over ? "border-ink bg-surface" : "border-rule"
        } ${disabled ? "opacity-50" : ""}`}
      >
        <p className="text-xs text-muted">
          Drop a page here, or{" "}
          <button
            type="button"
            onClick={() => inputRef.current?.click()}
            disabled={disabled}
            className="text-ink underline underline-offset-2 disabled:no-underline"
          >
            choose a file
          </button>
          .
        </p>
        <p className="mt-1.5 text-xs text-faint">
          PDF, PNG or JPEG · up to 10 pages · up to {MAX_UPLOAD_LABEL}
        </p>

        <input
          ref={inputRef}
          type="file"
          accept={ACCEPT_ATTRIBUTE}
          disabled={disabled}
          onChange={(event) => {
            offer(event.target.files?.[0]);
            // Reset so re-picking the same file after a rejection still fires.
            event.target.value = "";
          }}
          className="sr-only"
        />
      </div>

      {problem && (
        <p
          role="alert"
          className="mt-2 border-l-2 border-seal bg-seal-wash px-3 py-2 text-xs leading-relaxed text-seal"
        >
          {problem}
        </p>
      )}
    </div>
  );
}
