/**
 * Conversations, held entirely on the client.
 *
 * The backend stores nothing between requests — history and notes travel with
 * each ask. Keeping sessions here means "reset the demo" is just clearing
 * storage, with no server state that can leak from one run into the next.
 */

import { isAnswer } from "./types";
import type { Correction, ThreadItem } from "./types";

// Bumped when the stored shape changes. Old data is simply ignored rather
// than migrated -- a saved demo chat is not worth a migration path.
const STORAGE_KEY = "askdoc.conversations.v2";
const TITLE_LENGTH = 48;

export interface Conversation {
  id: string;
  docId: string;
  items: ThreadItem[];
  corrections: Correction[];
  createdAt: string;
}

export function newConversation(docId: string): Conversation {
  return {
    id:
      typeof crypto !== "undefined" && "randomUUID" in crypto
        ? crypto.randomUUID()
        : `c-${Date.now()}-${Math.random().toString(36).slice(2)}`,
    docId,
    items: [],
    corrections: [],
    createdAt: new Date().toISOString(),
  };
}

/** A conversation is named by the first thing said to it. */
export function titleFor(conversation: Conversation): string {
  const first = conversation.items[0];
  if (!first) return "New chat";
  const text = isAnswer(first) ? first.question : first.note;
  return text.length > TITLE_LENGTH ? `${text.slice(0, TITLE_LENGTH)}…` : text;
}

export function isEmpty(conversation: Conversation): boolean {
  return conversation.items.length === 0;
}

/** Only answered questions count — a remembered fact is not an answer. */
export function answerCount(conversation: Conversation): number {
  return conversation.items.filter(isAnswer).length;
}

export function load(): Conversation[] {
  if (typeof window === "undefined") return [];
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    const parsed: unknown = raw ? JSON.parse(raw) : [];
    if (!Array.isArray(parsed)) return [];
    // Defend against a half-written or hand-edited entry.
    return (parsed as Conversation[]).filter(
      (conversation) => Array.isArray(conversation?.items),
    );
  } catch {
    // Corrupt storage must never block the app from starting.
    return [];
  }
}

export function save(conversations: Conversation[]): void {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(conversations));
  } catch {
    // Quota or private mode. The session still works, it just won't persist.
  }
}

export function clearAll(): void {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.removeItem(STORAGE_KEY);
  } catch {
    // Nothing useful to do; the in-memory reset still happens.
  }
}
