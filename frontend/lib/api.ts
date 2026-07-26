/**
 * Thin client for the Python backend. One endpoint per verb, no state.
 */

import type { Correction, DigitisedDoc, ThreadItem, Turn } from "./types";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "http://127.0.0.1:8000";

class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE}${path}`, {
      ...init,
      headers: { "Content-Type": "application/json", ...init?.headers },
    });
  } catch {
    // A dead backend is a demo-time reality, so say so in words a viewer
    // can act on rather than surfacing a raw TypeError.
    throw new ApiError(`Cannot reach the backend at ${API_BASE}.`, 0);
  }

  if (!response.ok) {
    const detail = await response.text().catch(() => "");
    throw new ApiError(detail || `Request failed (${response.status}).`, response.status);
  }

  return (await response.json()) as T;
}

export function getDocument(docId: string): Promise<DigitisedDoc> {
  return request<DigitisedDoc>(`/documents/${encodeURIComponent(docId)}`);
}

export function listDocuments(): Promise<DigitisedDoc[]> {
  return request<DigitisedDoc[]>("/documents");
}

interface AskOptions {
  /** Earlier turns, oldest first, so follow-up questions resolve. */
  history?: Turn[];
  /** Reader notes that steer interpretation. */
  corrections?: Correction[];
}

/**
 * Send anything the reader types. The backend decides whether it is a
 * question to answer or a fact to remember, and the reply says which.
 *
 * It holds no session state, so everything needed to understand a follow-up
 * travels with the request. Reloading the page is a complete, reliable reset.
 */
export function ask(
  docId: string,
  question: string,
  { history = [], corrections = [] }: AskOptions = {},
): Promise<ThreadItem> {
  return request<ThreadItem>("/ask", {
    method: "POST",
    body: JSON.stringify({ doc_id: docId, question, history, corrections }),
  });
}

export { ApiError };
