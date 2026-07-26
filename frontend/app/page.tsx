"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { AppHeader } from "@/components/AppHeader";
import { DocumentList } from "@/components/DocumentList";
import { IngestionPanel } from "@/components/IngestionPanel";
import { ApiError, listDocuments } from "@/lib/api";
import type { DigitisedDoc } from "@/lib/types";
import { useIngestionJob } from "@/lib/useIngestionJob";

/**
 * Chats used to be saved here. They are not any more — the conversation now
 * lives and dies with the reader page, so the key is cleared once on the way
 * past rather than left behind as session state nothing reads.
 */
const RETIRED_STORE = "askdoc.conversations.v2";

/**
 * The library: what can I read?
 *
 * Answered before "ask me something", and answered in one place — a page you
 * brought and a page that shipped with the demo sit in the same list, because
 * to a reader they are the same kind of thing.
 *
 * Ingestion waits here. Where you dropped the file is where you are told what
 * happened to it, and nothing navigates to a reader until there is a document
 * to read.
 */
export default function Library() {
  const router = useRouter();
  const [documents, setDocuments] = useState<DigitisedDoc[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const ingestion = useIngestionJob((docId) => {
    router.push(`/doc/${encodeURIComponent(docId)}`);
  });

  useEffect(() => {
    let cancelled = false;

    try {
      window.localStorage.removeItem(RETIRED_STORE);
    } catch {
      // Private mode or a locked quota. Nothing depends on this.
    }

    listDocuments()
      .then((docs) => {
        if (cancelled) return;
        setDocuments(docs);
        setLoading(false);
      })
      .catch((cause: unknown) => {
        if (cancelled) return;
        setError(cause instanceof ApiError ? cause.message : "Could not load documents.");
        setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <div className="mx-auto flex min-h-screen max-w-[880px] flex-col">
      <AppHeader />

      <main className="flex-1 px-6 py-8">
        <section aria-label="Add a page">
          <p className="eyebrow">Add a page</p>
          <p className="mt-2 mb-3 max-w-[34rem] text-xs leading-relaxed text-muted">
            One dense official page — a circular, a notice, a clause. It is read once
            to work out what language it is in, then read again in that language.
          </p>
          <IngestionPanel ingestion={ingestion} />
        </section>

        <section className="mt-10" aria-label="Documents">
          <p className="eyebrow">Documents</p>
          <div className="mt-3">
            {loading ? (
              <p className="text-xs text-muted">Looking for pages…</p>
            ) : error ? (
              <p
                role="alert"
                className="border-l-2 border-seal bg-seal-wash px-3 py-2 text-xs leading-relaxed text-seal"
              >
                {error}
              </p>
            ) : (
              <DocumentList documents={documents} />
            )}
          </div>
        </section>
      </main>
    </div>
  );
}
