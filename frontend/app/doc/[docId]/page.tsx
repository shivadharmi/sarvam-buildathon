"use client";

import { useParams, useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";

import { AppHeader } from "@/components/AppHeader";
import { AskBox } from "@/components/AskBox";
import { ChatTurn } from "@/components/ChatTurn";
import { DocumentHeader } from "@/components/DocumentHeader";
import { MissingDocument } from "@/components/MissingDocument";
import { NoteTurn } from "@/components/NoteTurn";
import { NumberedDocument } from "@/components/NumberedDocument";
import { ReaderNotes } from "@/components/ReaderNotes";
import { StarterList } from "@/components/StarterList";
import { STARTER_NOTES } from "@/lib/questions";
import { isAnswer } from "@/lib/types";
import { useConversation } from "@/lib/useConversation";
import { useDocument } from "@/lib/useDocument";
import { useIngestionJob } from "@/lib/useIngestionJob";
import { useStarters } from "@/lib/useStarters";

/**
 * The reader: one document, at its own address.
 *
 * The address carries the document and nothing else. Reloading keeps the page
 * and drops the conversation — see lib/useConversation.ts — so a demo can be
 * reset to a known state by pressing reload, with no server session and no
 * saved notes to inherit.
 */
export default function Reader() {
  const params = useParams<{ docId: string }>();
  const docId = typeof params?.docId === "string" ? params.docId : "";
  const router = useRouter();

  const { doc, state, error: docError, reload } = useDocument(docId);
  const conversation = useConversation(docId);
  // Keyed on the digitisation, not just the id: a page re-read in another
  // language is a different reading with different line numbers.
  const starters = useStarters(doc?.doc_id ?? "", doc?.digitised_at);
  const [question, setQuestion] = useState("");
  const threadEndRef = useRef<HTMLDivElement>(null);

  // Re-reading the page in another language. Same document, new text — so the
  // thread is cleared rather than left pointing at lines that moved.
  const ingestion = useIngestionJob((readDocId) => {
    if (readDocId !== docId) {
      router.push(`/doc/${encodeURIComponent(readDocId)}`);
      return;
    }
    reload();
    conversation.startOver();
    setQuestion("");
  });

  const { items, answers, activeIndex, pending } = conversation;

  useEffect(() => {
    threadEndRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [items.length, pending]);

  if (state === "loading") {
    return (
      <div className="mx-auto flex min-h-screen max-w-[1600px] flex-col">
        <AppHeader back />
        <p className="px-6 py-8 text-xs text-muted">Opening the page…</p>
      </div>
    );
  }

  if (state !== "ready" || !doc) {
    return <MissingDocument docId={docId} state={state} error={docError} />;
  }

  const noteSuggestions = STARTER_NOTES[doc.doc_id] ?? [];
  const glossFor = (text: string): string | undefined =>
    starters.find((starter) => starter.text === text)?.gloss;
  // Mid-re-read, the text on screen is about to be replaced. Answering against
  // it would cite line numbers that are already on their way out.
  const locked = pending || ingestion.busy;

  return (
    // Fixed height with internal scrolling on desktop: each column scrolls on
    // its own so jumping to a citation never scrolls the input off screen.
    <div className="mx-auto flex min-h-screen max-w-[1600px] flex-col lg:h-screen lg:overflow-hidden">
      <AppHeader back />

      <main className="grid flex-1 grid-cols-1 lg:min-h-0 lg:grid-cols-[minmax(380px,460px)_1fr]">
        {/* ---- the conversation ---- */}
        <section
          className="flex flex-col border-b border-rule lg:min-h-0 lg:border-r lg:border-b-0"
          aria-label="Conversation"
        >
          <div className="shrink-0 border-b border-rule px-5 pt-2 pb-3">
            <ReaderNotes
              notes={conversation.corrections}
              suggestions={noteSuggestions}
              onAdd={conversation.addNote}
              onRemove={conversation.removeNote}
              disabled={locked}
            />

            {/* Clearing the thread without leaving the page. */}
            {!conversation.isEmpty && (
              <div className="mt-2 flex justify-end">
                <button
                  type="button"
                  onClick={conversation.startOver}
                  className="text-xs text-faint underline-offset-2 hover:text-seal hover:underline"
                >
                  Start over
                </button>
              </div>
            )}
          </div>

          {/* The thread grows downward; the newest reply stays in view. */}
          <div className="flex-1 lg:min-h-0 lg:overflow-y-auto">
            {items.length === 0 && !pending && (
              <StarterList
                starters={starters}
                onAsk={(text) => void conversation.submit(text)}
                disabled={locked}
              />
            )}

            <ul className="divide-y divide-rule-soft">
              {items.map((item, index) =>
                isAnswer(item) ? (
                  <ChatTurn
                    key={`${item.asked_at}-${index}`}
                    record={item}
                    gloss={glossFor(item.question)}
                    isActive={answers.indexOf(item) === activeIndex}
                    onSelect={() => conversation.pin(answers.indexOf(item))}
                  />
                ) : (
                  <NoteTurn key={`${item.asked_at}-${index}`} item={item} />
                ),
              )}
            </ul>

            {pending && <p className="px-5 py-4 text-xs text-muted">Reading the page…</p>}

            <div ref={threadEndRef} />
          </div>

          {/* Input pinned to the bottom, where a conversation expects it. */}
          <AskBox
            value={question}
            onChange={setQuestion}
            onSubmit={() => {
              void conversation.submit(question).then((sent) => {
                if (sent) setQuestion("");
              });
            }}
            docId={doc.doc_id}
            language={doc.language}
            disabled={locked}
            pending={pending}
            error={conversation.error}
          />
        </section>

        {/* ---- the page itself ---- */}
        <section className="flex min-w-0 flex-col lg:min-h-0" aria-label="The document">
          <DocumentHeader
            doc={doc}
            onChooseLanguage={ingestion.chooseLanguage}
            busy={ingestion.busy}
            status={ingestion.message}
            // A language was named outright here, so the detector should never
            // come back asking. If it does, say so — an unanswered question
            // with nothing on screen is the one outcome worse than a refusal.
            error={
              ingestion.error ??
              (ingestion.needsLanguage
                ? "Reading it in that language did not settle it. Try another one."
                : null)
            }
          />

          <div className="flex-1 py-4 lg:min-h-0 lg:overflow-y-auto">
            <NumberedDocument
              text={doc.text}
              citedFrom={conversation.activeRecord?.quote_from_line ?? null}
              citedTo={conversation.activeRecord?.quote_to_line ?? null}
            />
          </div>
        </section>
      </main>
    </div>
  );
}
