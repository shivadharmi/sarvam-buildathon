"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { AskBox } from "@/components/AskBox";
import { ChatSidebar } from "@/components/ChatSidebar";
import { ChatTurn } from "@/components/ChatTurn";
import { DocumentHeader } from "@/components/DocumentHeader";
import { DocumentSwitcher } from "@/components/DocumentSwitcher";
import { IngestionPanel } from "@/components/IngestionPanel";
import { NoteTurn } from "@/components/NoteTurn";
import { NumberedDocument } from "@/components/NumberedDocument";
import { ReaderNotes } from "@/components/ReaderNotes";
import { StarterList } from "@/components/StarterList";
import { ApiError, ask, getDocument, listDocuments } from "@/lib/api";
import * as store from "@/lib/conversations";
import type { Conversation } from "@/lib/conversations";
import { loadStarters, STARTER_NOTES } from "@/lib/questions";
import type { StarterQuestion } from "@/lib/questions";
import { isAnswer, toTurn } from "@/lib/types";
import type { DigitisedDoc } from "@/lib/types";
import { useIngestionJob } from "@/lib/useIngestionJob";

// Enough for a demo conversation without letting context grow unbounded.
const MAX_HISTORY_TURNS = 8;

export default function Home() {
  const [documents, setDocuments] = useState<DigitisedDoc[]>([]);
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [question, setQuestion] = useState("");
  // null means "follow the newest reply"; a number pins one turn.
  const [pinnedTurn, setPinnedTurn] = useState<number | null>(null);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [uploadOpen, setUploadOpen] = useState(false);
  const [starters, setStarters] = useState<StarterQuestion[]>([]);

  const threadEndRef = useRef<HTMLDivElement>(null);

  // Load documents and restore any saved chats. localStorage is read after
  // mount so the server and client render the same first paint.
  useEffect(() => {
    let cancelled = false;

    listDocuments()
      .then((docs) => {
        if (cancelled) return;
        setDocuments(docs);

        const saved = store.load();
        const firstDoc = docs[0]?.doc_id;
        if (saved.length > 0) {
          setConversations(saved);
          setActiveId(saved[0].id);
        } else if (firstDoc) {
          const fresh = store.newConversation(firstDoc);
          setConversations([fresh]);
          setActiveId(fresh.id);
        }
      })
      .catch((cause: unknown) =>
        setError(
          cause instanceof ApiError ? cause.message : "Could not load documents.",
        ),
      );

    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (conversations.length > 0) store.save(conversations);
  }, [conversations]);

  const active = conversations.find((c) => c.id === activeId) ?? null;
  const activeDoc = documents.find((doc) => doc.doc_id === active?.docId) ?? null;
  const thread = active?.items ?? [];
  // Only answers can be pinned — a remembered fact has no lines to show.
  const answers = thread.filter(isAnswer);
  const activeIndex = pinnedTurn ?? answers.length - 1;
  const activeRecord = answers[activeIndex] ?? null;
  const noteSuggestions = active ? (STARTER_NOTES[active.docId] ?? []) : [];

  // Hand-written for the demo pages, generated for uploads, and an empty list
  // when generation failed — which is a plain input, never an error.
  useEffect(() => {
    const docId = active?.docId;
    if (!docId) {
      setStarters([]);
      return;
    }

    let cancelled = false;
    setStarters([]);
    void loadStarters(docId).then((list) => {
      if (!cancelled) setStarters(list);
    });

    return () => {
      cancelled = true;
    };
    // digitised_at changes when a page is re-read in another language, and the
    // old suggestions were written against the old reading.
  }, [active?.docId, activeDoc?.digitised_at]);

  useEffect(() => {
    threadEndRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [thread.length, pending]);

  const update = useCallback(
    (id: string, change: (conversation: Conversation) => Conversation) => {
      setConversations((current) =>
        current.map((conversation) =>
          conversation.id === id ? change(conversation) : conversation,
        ),
      );
    },
    [],
  );

  const startNew = useCallback(
    (docId: string) => {
      const fresh = store.newConversation(docId);
      // Drop an untouched conversation rather than pile up empty shells.
      setConversations((current) => [
        fresh,
        ...current.filter((c) => !store.isEmpty(c)),
      ]);
      setActiveId(fresh.id);
      setPinnedTurn(null);
      setQuestion("");
      setError(null);
    },
    [],
  );

  /**
   * A newly digitised page becomes the live document.
   *
   * One document per conversation, always — so this starts a fresh one rather
   * than pointing the current chat at a page its earlier answers never saw.
   */
  const adopt = useCallback(
    async (docId: string) => {
      let loaded = await listDocuments().catch(() => null);
      if (!loaded) {
        // The list is a convenience; the page itself is the point, so fall
        // back to fetching just it.
        const doc = await getDocument(docId).catch(() => null);
        if (!doc) {
          setError("That page was read, but it could not be loaded. Try reloading.");
          return;
        }
        loaded = [...documents.filter((existing) => existing.doc_id !== docId), doc];
      }
      setDocuments(loaded);
      setUploadOpen(false);
      startNew(docId);
    },
    [documents, startNew],
  );

  const ingestion = useIngestionJob((docId) => void adopt(docId));

  const switchDocument = (docId: string) => {
    if (!active) return startNew(docId);
    // An untouched chat just changes subject; a used one stays intact, and the
    // new page starts its own. A question never reaches across two documents.
    if (store.isEmpty(active)) {
      // Notes go too: "I'm applying to the Maldakal project" was said about a
      // particular page, and carrying it to another one is context the reader
      // never gave about that page.
      update(active.id, (conversation) => ({ ...conversation, docId, corrections: [] }));
      setPinnedTurn(null);
    } else {
      startNew(docId);
    }
  };

  const toggleUpload = () => {
    // Closing the panel clears a stale rejection, but never a live job.
    if (uploadOpen && !ingestion.busy) ingestion.reset();
    setUploadOpen(!uploadOpen);
  };

  // The panel outlives the toggle while there is something in flight or a
  // language question still unanswered.
  const showIngestion = uploadOpen || ingestion.busy || ingestion.needsLanguage;

  const submit = useCallback(
    async (text: string) => {
      if (!active || !activeDoc || !text.trim() || pending) return;

      const conversationId = active.id;
      setPending(true);
      setError(null);
      try {
        const history = active.items
          .filter(isAnswer)
          .slice(-MAX_HISTORY_TURNS)
          .map(toTurn);

        const item = await ask(active.docId, text.trim(), {
          history,
          corrections: active.corrections,
        });

        update(conversationId, (conversation) => ({
          ...conversation,
          items: [...conversation.items, item],
          // A statement becomes active memory as well as a thread entry: the
          // conversation records that it was said, the note panel governs
          // whether it is still being applied.
          corrections: isAnswer(item)
            ? conversation.corrections
            : [...conversation.corrections, { note: item.note }],
        }));
        setPinnedTurn(null);
        setQuestion("");
      } catch (cause: unknown) {
        setError(
          cause instanceof ApiError
            ? cause.message
            : "Something went wrong asking that question.",
        );
      } finally {
        setPending(false);
      }
    },
    [active, activeDoc, pending, update],
  );

  const addCorrection = (note: string) => {
    if (!active) return;
    update(active.id, (conversation) => ({
      ...conversation,
      corrections: [...conversation.corrections, { note }],
    }));
  };

  const removeCorrection = (index: number) => {
    if (!active) return;
    update(active.id, (conversation) => ({
      ...conversation,
      corrections: conversation.corrections.filter((_, i) => i !== index),
    }));
  };

  const deleteConversation = (id: string) => {
    setConversations((current) => {
      const remaining = current.filter((c) => c.id !== id);
      if (id === activeId) {
        setActiveId(remaining[0]?.id ?? null);
        setPinnedTurn(null);
      }
      return remaining;
    });
  };

  const clearAll = () => {
    store.clearAll();
    const docId = active?.docId ?? documents[0]?.doc_id;
    if (!docId) return setConversations([]);
    const fresh = store.newConversation(docId);
    setConversations([fresh]);
    setActiveId(fresh.id);
    setPinnedTurn(null);
  };

  const glossFor = (text: string): string | undefined =>
    starters.find((starter) => starter.text === text)?.gloss;

  return (
    // Fixed height with internal scrolling on desktop: each column scrolls on
    // its own so jumping to a citation never scrolls the input off screen.
    <div className="mx-auto flex min-h-screen max-w-[1600px] flex-col lg:h-screen lg:overflow-hidden">
      <header className="flex shrink-0 flex-wrap items-baseline gap-x-6 gap-y-2 border-b border-rule px-6 py-4">
        <h1 className="text-[0.9375rem] font-semibold tracking-tight">
          Ask the Document
        </h1>
        <p className="text-xs text-muted">
          Every answer shows the line it came from — or says the page doesn&apos;t say.
        </p>

        <DocumentSwitcher
          documents={documents}
          activeDocId={active?.docId ?? null}
          onSwitch={switchDocument}
          onToggleUpload={toggleUpload}
          uploadOpen={showIngestion}
        />
      </header>

      {showIngestion && <IngestionPanel ingestion={ingestion} />}

      <main className="grid flex-1 grid-cols-1 lg:min-h-0 lg:grid-cols-[210px_minmax(380px,440px)_1fr]">
        <ChatSidebar
          conversations={conversations}
          documents={documents}
          activeId={activeId}
          onSelect={(id) => {
            setActiveId(id);
            setPinnedTurn(null);
          }}
          onNew={() => startNew(active?.docId ?? documents[0]?.doc_id ?? "doc_a")}
          onDelete={deleteConversation}
          onClearAll={clearAll}
        />

        {/* ---- the conversation ---- */}
        <section
          className="flex flex-col border-b border-rule lg:min-h-0 lg:border-r lg:border-b-0"
          aria-label="Conversation"
        >
          <div className="shrink-0 border-b border-rule px-5 pt-2 pb-3">
            <ReaderNotes
              notes={active?.corrections ?? []}
              suggestions={noteSuggestions}
              onAdd={addCorrection}
              onRemove={removeCorrection}
              disabled={!activeDoc || pending}
            />
          </div>

          {/* The thread grows downward; the newest reply stays in view. */}
          <div className="flex-1 lg:min-h-0 lg:overflow-y-auto">
            {thread.length === 0 && !pending && (
              <StarterList
                starters={starters}
                onAsk={(text) => void submit(text)}
                disabled={pending}
              />
            )}

            <ul className="divide-y divide-rule-soft">
              {thread.map((item, index) =>
                isAnswer(item) ? (
                  <ChatTurn
                    key={`${item.asked_at}-${index}`}
                    record={item}
                    gloss={glossFor(item.question)}
                    isActive={answers.indexOf(item) === activeIndex}
                    onSelect={() => setPinnedTurn(answers.indexOf(item))}
                  />
                ) : (
                  <NoteTurn key={`${item.asked_at}-${index}`} item={item} />
                ),
              )}
            </ul>

            {pending && (
              <p className="px-5 py-4 text-xs text-muted">Reading the page…</p>
            )}

            <div ref={threadEndRef} />
          </div>

          {/* Input pinned to the bottom, where a conversation expects it. */}
          <AskBox
            value={question}
            onChange={setQuestion}
            onSubmit={() => void submit(question)}
            language={activeDoc?.language}
            disabled={!activeDoc || pending}
            pending={pending}
            error={error}
          />
        </section>

        {/* ---- the page itself ---- */}
        <section className="flex min-w-0 flex-col lg:min-h-0" aria-label="The document">
          <DocumentHeader
            doc={activeDoc}
            onChooseLanguage={ingestion.chooseLanguage}
            busy={ingestion.busy}
          />

          <div className="flex-1 py-4 lg:min-h-0 lg:overflow-y-auto">
            {activeDoc ? (
              <NumberedDocument
                text={activeDoc.text}
                citedFrom={activeRecord?.quote_from_line ?? null}
                citedTo={activeRecord?.quote_to_line ?? null}
              />
            ) : (
              <p className="px-6 text-sm leading-relaxed text-muted">
                No page loaded. Add one with{" "}
                <span className="text-ink">+ Add a page</span>, or run{" "}
                <code className="font-mono text-xs">askdoc.cli digitise --doc doc_a</code>{" "}
                for the demo documents.
              </p>
            )}
          </div>
        </section>
      </main>
    </div>
  );
}
