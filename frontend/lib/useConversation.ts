"use client";

/**
 * One conversation about one document, held for as long as the page is open.
 *
 * ⚠️ Deliberately not persisted, and this is a change from the earlier
 * single-page build, which saved chats to localStorage.
 *
 * The backend stores nothing between requests — history and notes travel with
 * every ask — and this is the client half of the same promise. The document is
 * addressable; what was said about it is not. So reloading /doc/<id> keeps the
 * page and drops the conversation, which is exactly the reliable reset the
 * demo depends on: no run can inherit a stale note from the run before it.
 *
 * The cost is real and is not hidden: closing the tab loses the thread. That
 * is the right trade for a tool whose whole claim is that it does not carry
 * over anything it was not just told.
 */

import { useCallback, useState } from "react";

import { ApiError, ask } from "./api";
import { isAnswer, toTurn } from "./types";
import type { AnswerRecord, Correction, ThreadItem } from "./types";

// Enough for a demo conversation without letting context grow unbounded.
const MAX_HISTORY_TURNS = 8;

export interface ConversationHandle {
  items: ThreadItem[];
  /** Answered questions only — a remembered fact has no lines to show. */
  answers: AnswerRecord[];
  corrections: Correction[];
  pending: boolean;
  error: string | null;
  /** null means "follow the newest reply"; a number pins one turn. */
  pinned: number | null;
  /** The answer whose lines the document column is highlighting. */
  activeRecord: AnswerRecord | null;
  activeIndex: number;
  /** Resolves true when a reply was recorded — false leaves the draft alone. */
  submit: (text: string) => Promise<boolean>;
  addNote: (note: string) => void;
  removeNote: (index: number) => void;
  pin: (index: number | null) => void;
  startOver: () => void;
  isEmpty: boolean;
}

export function useConversation(docId: string): ConversationHandle {
  const [items, setItems] = useState<ThreadItem[]>([]);
  const [corrections, setCorrections] = useState<Correction[]>([]);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [pinned, setPinned] = useState<number | null>(null);

  // Next reuses this component when the address moves from one document to
  // another — only the param changes — so the reset has to be written down
  // rather than assumed. Done during render, not in an effect: an effect would
  // paint one frame of the old document's answers against the new page.
  const [openDoc, setOpenDoc] = useState(docId);
  if (openDoc !== docId) {
    setOpenDoc(docId);
    setItems([]);
    setCorrections([]);
    setPinned(null);
    setError(null);
    setPending(false);
  }

  const startOver = useCallback(() => {
    setItems([]);
    setCorrections([]);
    setPinned(null);
    setError(null);
  }, []);

  const submit = useCallback(
    async (text: string): Promise<boolean> => {
      const question = text.trim();
      if (!question || pending) return false;

      setPending(true);
      setError(null);
      try {
        const history = items.filter(isAnswer).slice(-MAX_HISTORY_TURNS).map(toTurn);
        const item = await ask(docId, question, { history, corrections });

        setItems((current) => [...current, item]);
        // A statement becomes active memory as well as a thread entry: the
        // conversation records that it was said, the note panel governs
        // whether it is still being applied.
        if (!isAnswer(item)) {
          setCorrections((current) => [...current, { note: item.note }]);
        }
        setPinned(null);
        return true;
      } catch (cause: unknown) {
        setError(
          cause instanceof ApiError
            ? cause.message
            : "Something went wrong asking that question.",
        );
        // The question stays in the box: a failed send is not a reason to make
        // someone retype what they asked.
        return false;
      } finally {
        setPending(false);
      }
    },
    [corrections, docId, items, pending],
  );

  const addNote = useCallback((note: string) => {
    setCorrections((current) => [...current, { note }]);
  }, []);

  const removeNote = useCallback((index: number) => {
    setCorrections((current) => current.filter((_, at) => at !== index));
  }, []);

  const answers = items.filter(isAnswer);
  const activeIndex = pinned ?? answers.length - 1;

  return {
    items,
    answers,
    corrections,
    pending,
    error,
    pinned,
    activeRecord: answers[activeIndex] ?? null,
    activeIndex,
    submit,
    addNote,
    removeNote,
    pin: setPinned,
    startOver,
    isEmpty: items.length === 0 && corrections.length === 0,
  };
}
