"use client";

import { use, useEffect, useState } from "react";
import Link from "next/link";

import { NumberedDocument } from "@/components/NumberedDocument";
import { ApiError, getRecord } from "@/lib/api";
import type { SharedRecord } from "@/lib/types";

const REFUSAL_HEADLINE: Record<string, string> = {
  document_silent: "This page doesn't say.",
  not_relevant: "This page doesn't say.",
  citation_invalid: "Couldn't verify a citation.",
};

/**
 * One saved answer, opened from a link.
 *
 * Deliberately not a chat. The artifact this product produces is a single
 * verifiable record — a question, an answer, and the lines of the page it came
 * from — and a shared link shows exactly that, with the document beside it so
 * the reader checks rather than trusts. There is no input box: the record is
 * immutable, and offering to continue would suggest otherwise.
 */
export default function SharedRecordPage({
  params,
}: {
  params: Promise<{ recordId: string }>;
}) {
  const { recordId } = use(params);
  const [shared, setShared] = useState<SharedRecord | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let live = true;
    getRecord(recordId)
      .then((result) => live && setShared(result))
      .catch((caught) =>
        live &&
        setError(caught instanceof ApiError ? caught.message : "Couldn't open that link."),
      );
    return () => {
      live = false;
    };
  }, [recordId]);

  if (error) {
    return (
      <main className="mx-auto max-w-2xl px-6 py-16">
        <p className="border-l-2 border-seal bg-seal-wash px-4 py-3 text-sm text-seal">
          {error}
        </p>
        <Link href="/" className="mt-6 inline-block text-xs text-faint hover:text-ink">
          ← Read a document
        </Link>
      </main>
    );
  }

  if (!shared) {
    return <main className="mx-auto max-w-2xl px-6 py-16 text-sm text-faint">Opening…</main>;
  }

  const { record, document: doc } = shared;
  const cited = record.status === "cited";
  const lineLabel =
    record.quote_from_line === record.quote_to_line
      ? `Line ${record.quote_from_line}`
      : `Lines ${record.quote_from_line}–${record.quote_to_line}`;

  return (
    <div className="min-h-screen">
      <header className="border-b border-rule px-6 py-4">
        <Link href="/" className="text-sm font-medium text-ink">
          Ask the Document
        </Link>
        <p className="mt-0.5 text-xs text-faint">
          A saved answer. The page it came from is shown below, so you can check it.
        </p>
      </header>

      <main className="grid gap-8 px-6 py-8 lg:grid-cols-2">
        <section aria-label="The answer">
          <p className="eyebrow text-faint">Question</p>
          <p className="font-indic mt-1 text-[0.95rem] leading-snug text-ink">
            {record.question}
          </p>

          <div
            className={`mt-6 border-l-2 py-2 pl-4 ${cited ? "border-duplicator" : "border-seal"}`}
          >
            {cited ? (
              <>
                <p className="font-indic text-[0.95rem] leading-relaxed text-ink">
                  {record.answer}
                </p>
                <p className="eyebrow mt-3 text-duplicator">
                  {lineLabel} of this page
                  {record.citation_is_broad && (
                    <span className="text-faint">
                      {" · "}
                      {record.quote_line_count} lines, a large part of it
                    </span>
                  )}
                </p>
              </>
            ) : (
              <p className="text-[0.95rem] font-medium text-seal">
                {REFUSAL_HEADLINE[record.refusal_reason ?? ""] ?? "No answer shown."}
              </p>
            )}
          </div>

          {/* The provenance, stated rather than implied. */}
          <dl className="mt-8 space-y-1.5 text-xs text-faint">
            <div className="flex gap-2">
              <dt className="w-20 shrink-0">Document</dt>
              <dd className="text-muted">{doc.label || doc.source_filename}</dd>
            </div>
            <div className="flex gap-2">
              <dt className="w-20 shrink-0">Answered</dt>
              <dd className="text-muted">{record.asked_at.replace("T", " ")}</dd>
            </div>
            <div className="flex gap-2">
              <dt className="w-20 shrink-0">Model</dt>
              <dd className="text-muted">{record.model}</dd>
            </div>
          </dl>

          <p className="mt-6 max-w-prose text-xs leading-relaxed text-faint">
            The quote was not written by the model. It points at line numbers, and the
            text is sliced out of the digitised page shown here — re-checked against it
            when this link was opened.
          </p>

          <Link
            href={`/doc/${doc.doc_id}`}
            className="mt-6 inline-block text-xs text-duplicator underline-offset-2 hover:underline"
          >
            Ask this page something →
          </Link>
        </section>

        <section aria-label="The document" className="min-w-0">
          <NumberedDocument
            text={doc.text}
            citedFrom={record.quote_from_line}
            citedTo={record.quote_to_line}
          />
        </section>
      </main>
    </div>
  );
}
