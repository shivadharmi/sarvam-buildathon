/**
 * Thin client for the Python backend. One endpoint per verb, no state.
 */

import type {
  Correction,
  DigitisedDoc,
  GeneratedStarter,
  JobStatus,
  Speech,
  SpeechSource,
  SharedRecord,
  ThreadItem,
  Transcript,
  Turn,
  UploadAccepted,
} from "./types";

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

/**
 * Dig the server's own sentence out of an error body.
 *
 * An upload rejection is written for the reader ("That file is 41 MB. I can
 * take up to 25 MB.") and must reach them in those words, not as
 * `{"detail":"..."}`. A body we cannot read as a message is replaced rather
 * than dumped — a stack trace or an HTML error page is noise, not an answer.
 */
function messageFrom(body: string, status: number): string {
  const generic = `Request failed (${status}).`;
  const trimmed = body.trim();
  if (!trimmed) return generic;

  try {
    const parsed: unknown = JSON.parse(trimmed);
    if (parsed && typeof parsed === "object") {
      const detail = (parsed as { detail?: unknown; message?: unknown }).detail;
      const message = (parsed as { message?: unknown }).message;
      for (const candidate of [detail, message]) {
        if (typeof candidate === "string" && candidate.trim()) return candidate.trim();
        if (candidate && typeof candidate === "object") {
          const nested = (candidate as { message?: unknown }).message;
          if (typeof nested === "string" && nested.trim()) return nested.trim();
        }
      }
    }
  } catch {
    // Not JSON. A short plain-text body is still worth showing.
  }

  if (trimmed.startsWith("<") || trimmed.length > 300) return generic;
  return trimmed;
}

/** A parsed body plus the response, for the few calls that read a header. */
async function requestWith<T>(path: string, init?: RequestInit) {
  const response = await rawRequest(path, init);
  return { body: (await response.json()) as T, response };
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  return (await requestWith<T>(path, init)).body;
}

async function rawRequest(path: string, init?: RequestInit): Promise<Response> {
  // The browser has to set multipart's boundary itself, so an explicit
  // Content-Type on a FormData body would make the upload unparseable.
  const isForm = typeof FormData !== "undefined" && init?.body instanceof FormData;

  let response: Response;
  try {
    response = await fetch(`${API_BASE}${path}`, {
      ...init,
      headers: {
        ...(isForm ? {} : { "Content-Type": "application/json" }),
        ...init?.headers,
      },
    });
  } catch {
    // A dead backend is a demo-time reality, so say so in words a viewer
    // can act on rather than surfacing a raw TypeError.
    throw new ApiError(`Cannot reach the backend at ${API_BASE}.`, 0);
  }

  if (!response.ok) {
    const body = await response.text().catch(() => "");
    throw new ApiError(messageFrom(body, response.status), response.status);
  }

  return response;
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
export async function ask(
  docId: string,
  question: string,
  { history = [], corrections = [] }: AskOptions = {},
): Promise<ThreadItem> {
  const { body, response } = await requestWith<ThreadItem>("/ask", {
    method: "POST",
    body: JSON.stringify({ doc_id: docId, question, history, corrections }),
  });
  // The backend stores every answer and names it in a header, so the record
  // can be shared without a second round trip.
  const recordId = response.headers.get("X-Record-Id");
  return body.kind === "answer" && recordId ? { ...body, record_id: recordId } : body;
}

/** Open a shared answer record, with the page needed to check it. */
export function getRecord(recordId: string): Promise<SharedRecord> {
  return request<SharedRecord>(`/records/${encodeURIComponent(recordId)}`);
}

/**
 * Hand a page to the backend. Returns a job to poll — or, when these exact
 * bytes were digitised before, a finished document and no paid call.
 */
export function uploadDocument(file: File): Promise<UploadAccepted> {
  const form = new FormData();
  form.append("file", file, file.name);
  return request<UploadAccepted>("/documents", { method: "POST", body: form });
}

export function getJob(jobId: string): Promise<JobStatus> {
  return request<JobStatus>(`/jobs/${encodeURIComponent(jobId)}`);
}

/**
 * Say what language the page is in — either answering a `needs_language` job,
 * or overruling a detection that got it wrong. Re-digitises, so it returns a
 * job like an upload does.
 */
export function setDocumentLanguage(
  docId: string,
  language: string,
): Promise<UploadAccepted> {
  return request<UploadAccepted>(`/documents/${encodeURIComponent(docId)}/language`, {
    method: "POST",
    body: JSON.stringify({ language }),
  });
}

/** Generated starters for an uploaded page. An empty list is a valid answer. */
export function getStarters(docId: string): Promise<GeneratedStarter[]> {
  return request<GeneratedStarter[]>(
    `/documents/${encodeURIComponent(docId)}/starters`,
  );
}

/**
 * Turn a recording into text. Returns the words and nothing else — asking them
 * is the reader's decision, made after they have seen what we heard.
 *
 * `docId` is required because we already know which page is open, so the
 * recogniser is told the language rather than left to guess it.
 */
export async function transcribe(docId: string, audio: Blob, filename: string) {
  const form = new FormData();
  form.append("file", audio, filename);
  form.append("doc_id", docId);
  const { transcript } = await request<Transcript>("/transcribe", {
    method: "POST",
    body: form,
  });
  return transcript;
}

interface SpeakTarget {
  source: SpeechSource;
  /** source="quote": offsets into the document, as the record reported them. */
  quoteStart?: number | null;
  quoteEnd?: number | null;
  /** source="answer": the prose on screen. */
  text?: string;
}

/**
 * Read the citation, or the answer, aloud.
 *
 * A quote is requested by *offset*, never by text: the backend re-slices it
 * from its own copy of the page, so nothing here can put words in the
 * document's mouth. Audio has no visual distinction between the page's words
 * and the model's, which is exactly why that has to hold on this path too.
 */
export function speak(docId: string, target: SpeakTarget): Promise<Speech> {
  return request<Speech>("/speak", {
    method: "POST",
    body: JSON.stringify({
      doc_id: docId,
      source: target.source,
      quote_start: target.quoteStart ?? null,
      quote_end: target.quoteEnd ?? null,
      text: target.text ?? "",
    }),
  });
}

export { ApiError };
