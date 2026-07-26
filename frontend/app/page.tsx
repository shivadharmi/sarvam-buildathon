"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { ChatSidebar } from "@/components/ChatSidebar";
import { ChatTurn } from "@/components/ChatTurn";
import { NoteTurn } from "@/components/NoteTurn";
import { NumberedDocument } from "@/components/NumberedDocument";
import { ReaderNotes } from "@/components/ReaderNotes";
import { ApiError, ask, listDocuments } from "@/lib/api";
import * as store from "@/lib/conversations";
import type { Conversation } from "@/lib/conversations";
import { DOCUMENT_LABELS, STARTER_NOTES, STARTER_QUESTIONS } from "@/lib/questions";
import { isAnswer, toTurn } from "@/lib/types";
import type { DigitisedDoc } from "@/lib/types";

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
  const starters = active ? (STARTER_QUESTIONS[active.docId] ?? []) : [];
  const noteSuggestions = active ? (STARTER_NOTES[active.docId] ?? []) : [];

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

  const switchDocument = (docId: string) => {
    if (!active) return startNew(docId);
    // An untouched chat just changes subject; a used one stays intact.
    if (store.isEmpty(active)) {
      update(active.id, (conversation) => ({ ...conversation, docId }));
      setPinnedTurn(null);
    } else {
      startNew(docId);
    }
  };

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

        <nav className="ml-auto flex gap-1" aria-label="Choose a document">
          {documents.map((doc) => {
            const isActive = doc.doc_id === active?.docId;
            return (
              <button
                key={doc.doc_id}
                type="button"
                onClick={() => switchDocument(doc.doc_id)}
                aria-current={isActive ? "page" : undefined}
                className={`px-3 py-1.5 text-xs transition-colors ${
                  isActive
                    ? "bg-ink text-paper"
                    : "text-muted hover:bg-surface hover:text-ink"
                }`}
              >
                {DOCUMENT_LABELS[doc.doc_id]?.script ?? doc.doc_id}
              </button>
            );
          })}
        </nav>
      </header>

      <main className="grid flex-1 grid-cols-1 lg:min-h-0 lg:grid-cols-[210px_minmax(380px,440px)_1fr]">
        <ChatSidebar
          conversations={conversations}
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
              <div className="px-5 py-5">
                <p className="eyebrow">Ask this page anything</p>
                <p className="mt-2 text-xs leading-relaxed text-muted">
                  Follow-ups work — ask &ldquo;and the age limit?&rdquo; after a first
                  answer and it knows what you mean.
                </p>
                <ul className="mt-4 space-y-1">
                  {starters.map((starter) => (
                    <li key={starter.text}>
                      <button
                        type="button"
                        onClick={() => void submit(starter.text)}
                        disabled={pending}
                        className="w-full px-2 py-1.5 text-left transition-colors hover:bg-surface disabled:opacity-40"
                      >
                        <span className="font-indic block text-[0.8125rem] leading-snug text-ink">
                          {starter.text}
                        </span>
                        <span className="mt-0.5 block text-xs text-faint">
                          {starter.gloss}
                          {starter.unanswerable && " — not on this page"}
                          {starter.needsNote && " — needs a note above"}
                        </span>
                      </button>
                    </li>
                  ))}
                </ul>
              </div>
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
          <div className="shrink-0 border-t border-rule px-5 py-4">
            <form
              onSubmit={(event) => {
                event.preventDefault();
                void submit(question);
              }}
            >
              <label htmlFor="question" className="sr-only">
                Ask this page
              </label>
              <div className="flex gap-2">
                <input
                  id="question"
                  value={question}
                  onChange={(event) => setQuestion(event.target.value)}
                  placeholder={
                    activeDoc?.language === "te-IN" ? "మీ ప్రశ్న…" : "உங்கள் கேள்வி…"
                  }
                  disabled={!activeDoc || pending}
                  className="font-indic min-w-0 flex-1 border border-rule bg-surface px-3 py-2 text-sm outline-none placeholder:text-faint focus:border-duplicator disabled:opacity-50"
                />
                <button
                  type="submit"
                  disabled={!activeDoc || pending || !question.trim()}
                  className="shrink-0 bg-duplicator px-4 py-2 text-xs font-medium text-white transition-opacity disabled:opacity-40"
                >
                  {pending ? "Checking…" : "Ask"}
                </button>
              </div>
            </form>

            {error && (
              <p
                role="alert"
                className="mt-3 border-l-2 border-seal bg-seal-wash px-3 py-2 text-xs text-seal"
              >
                {error}
              </p>
            )}
          </div>
        </section>

        {/* ---- the page itself ---- */}
        <section className="flex min-w-0 flex-col lg:min-h-0" aria-label="The document">
          <div className="flex shrink-0 flex-wrap items-baseline justify-between gap-x-4 gap-y-1 border-b border-rule px-6 py-3">
            <p className="eyebrow">
              {activeDoc ? DOCUMENT_LABELS[activeDoc.doc_id]?.name : "No document"}
            </p>
            <p className="text-xs text-faint">
              {activeDoc
                ? `digitised from a scan · ${activeDoc.text.split("\n").length} lines`
                : ""}
            </p>
          </div>

          <div className="flex-1 py-4 lg:min-h-0 lg:overflow-y-auto">
            {activeDoc ? (
              <NumberedDocument
                text={activeDoc.text}
                citedFrom={activeRecord?.quote_from_line ?? null}
                citedTo={activeRecord?.quote_to_line ?? null}
              />
            ) : (
              <p className="px-6 text-sm text-muted">
                Nothing digitised yet. Run{" "}
                <code className="font-mono text-xs">askdoc.cli digitise --doc doc_a</code>.
              </p>
            )}
          </div>
        </section>
      </main>
    </div>
  );
}
