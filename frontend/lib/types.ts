/**
 * Mirrors backend/askdoc/models.py. Keep the two in sync by hand -- the
 * contract is small on purpose so that stays cheap.
 */

/**
 * Two states only. There is deliberately no "low confidence" middle ground:
 * either a verbatim source span backs the answer, or the document does not say.
 */
export type AnswerStatus = "cited" | "not_stated";

/**
 * Why an answer was not cited.
 *
 * Only "document_silent" is a claim about the page. The others are limits of
 * ours, and showing them as silence would tell the reader the page lacks
 * something it actually contains. Never collapse these into one message.
 */
export type RefusalReason = "document_silent" | "citation_invalid" | "not_relevant";

/**
 * The reader told the page something instead of asking it something.
 *
 * Deliberately not an AnswerStatus: that describes what the *document* says,
 * and there are only two such states. "Noted" is not a claim about the
 * document at all.
 */
export interface NoteAcknowledgement {
  kind: "note";
  doc_id: string;
  note: string;
  acknowledgement: string;
  asked_at: string;
}

export interface AnswerRecord {
  kind: "answer";
  question: string;
  answer: string;
  status: AnswerStatus;
  doc_id: string;

  /**
   * The citation, sliced by the backend out of DigitisedDoc.text at the lines
   * the model pointed to. Never text the model wrote. Present only when
   * status is "cited".
   */
  quote: string | null;
  /** Character offsets into DigitisedDoc.text. */
  quote_start: number | null;
  quote_end: number | null;
  /** 1-based inclusive line numbers — what the UI highlights. */
  quote_from_line: number | null;
  quote_to_line: number | null;

  /**
   * How much of the page the citation covers.
   *
   * Breadth used to refuse the answer outright. It doesn't any more: a wide
   * citation is weaker evidence, not false evidence, and withholding a verified
   * answer over it told the reader the page was silent about something it
   * covers at length. Shown, so they can weigh it themselves.
   */
  quote_line_count: number;
  citation_is_broad: boolean;

  model: string;
  asked_at: string;

  /**
   * Set once the answer has been stored, so it can be shared.
   *
   * Client-side only — it arrives on a response header, not in the body, and
   * is never sent back. A shared record is immutable; this just names it.
   */
  record_id?: string;

  /** What the model claimed before verification ruled. Powers the honesty beat. */
  model_claimed_found: boolean;
  model_claimed_quote: string | null;
  refusal_reason: RefusalReason | null;
  rejection_detail: string | null;

  /**
   * False when the model's own wording didn't match the lines it pointed at.
   * A transparency signal, not a gate — the extracted lines are shown either way.
   */
  model_quote_matched: boolean | null;
}

/**
 * One earlier exchange. The backend replays these as real user/assistant
 * messages so a follow-up resolves. Never a source for an answer — the
 * citation still comes from the document.
 */
export interface Turn {
  question: string;
  answer: string;
  status: AnswerStatus;
  quote_from_line: number;
  quote_to_line: number;
}

/** One entry in the conversation: an answered question, or a remembered fact. */
export type ThreadItem = AnswerRecord | NoteAcknowledgement;

export function isAnswer(item: ThreadItem): item is AnswerRecord {
  return item.kind === "answer";
}

/** Reduce a finished answer to what the next question needs to know. */
export function toTurn(record: AnswerRecord): Turn {
  return {
    question: record.question,
    answer: record.answer,
    status: record.status,
    quote_from_line: record.quote_from_line ?? 0,
    quote_to_line: record.quote_to_line ?? 0,
  };
}

/** A note the reader adds to steer interpretation. Never quotable. */
export interface Correction {
  note: string;
}

/**
 * What the speech recogniser heard.
 *
 * Deliberately just text, and deliberately not an answer. A misheard question
 * would otherwise produce a fully verified citation for something the reader
 * never asked — correct by every check we run, and still wrong. So this goes
 * into the input box for them to read before anything is asked.
 */
export interface Transcript {
  transcript: string;
}

/** Which of the two things on screen to read aloud. */
export type SpeechSource = "quote" | "answer";

/** Base64 WAV clips, played in order. Long text comes back as several. */
export interface Speech {
  audios: string[];
  language: string;
  /**
   * True when the text was longer than the service will read.
   *
   * Surfaced, never silent: audio that simply stops is indistinguishable from
   * a page that simply ends, and letting someone believe they heard the whole
   * citation when they didn't is the same failure as calling our own limit the
   * document's silence.
   */
  truncated: boolean;
}

/** Where a document came from. Builtins are the two cached demo pages. */
export type DocumentOrigin = "builtin" | "upload";

/**
 * How we arrived at the document's language.
 *
 * This is shown to the reader, and the distinction is the same honesty beat as
 * a refusal reason: "detected" and "script" are claims we made, "user" is a
 * claim the reader made. Someone who can see we guessed can correct us;
 * someone who can see we asked knows we did not guess.
 */
export type LanguageSource = "builtin" | "user" | "detected" | "script";

export interface DigitisedDoc {
  doc_id: string;
  language: string;
  /** NFC-normalised. Quote offsets index into this exact string. */
  text: string;
  source_filename: string;
  digitised_at: string;
  page_count: number;

  /**
   * Added with uploads. Optional on the wire because the two cached demo
   * documents were written before these existed — the backend defaults them,
   * but a stale cache file must never blank the whole document list.
   */
  origin?: DocumentOrigin;
  label?: string;
  language_source?: LanguageSource;
  probe_language?: string;
}

/**
 * A starter question the backend generated for an uploaded page.
 *
 * Model-authored *input*, never a citation: asking one runs the same
 * line-anchored gate as anything the reader types.
 */
export interface GeneratedStarter {
  text: string;
  gloss: string;
}

/**
 * Ingestion progress. `stage` is the fine-grained step; `state` is the coarse
 * one, and either may carry the terminal value — read both, trust neither
 * alone.
 */
export type JobStage =
  | "validating"
  | "digitising_probe"
  | "detecting"
  | "digitising_final"
  | "ready"
  | "failed"
  | "needs_language";

export type JobState = "pending" | "running" | "ready" | "failed" | "needs_language";

export interface JobStatus {
  job_id?: string;
  state: JobState;
  stage: JobStage;
  /** What detection proposed, once it has. Null until then. */
  detected_language?: string | null;
  /** Our own dominant-script reading, e.g. "Taml". */
  script?: string | null;
  doc_id?: string | null;
  /** Plain-language reason, shown verbatim. Only set when the job failed. */
  error?: string | null;
}

/** 202 with a job to poll, or 200 when the same bytes were already digitised. */
export interface UploadAccepted {
  job_id: string;
  doc_id?: string | null;
  state?: JobState;
}

/**
 * `needs_language` is terminal but not a failure — it is the detector
 * declining to guess between languages that share a script, which the UI
 * answers with a picker.
 */
export type JobOutcome = "ready" | "failed" | "needs_language";

const TERMINAL: ReadonlySet<string> = new Set<string>([
  "ready",
  "failed",
  "needs_language",
]);

export function jobOutcome(job: JobStatus): JobOutcome | null {
  // Failure first: a job that both failed and reports a stale stage is failed.
  if (job.state === "failed" || job.stage === "failed") return "failed";
  if (job.state === "needs_language" || job.stage === "needs_language") {
    return "needs_language";
  }
  if (job.state === "ready" || job.stage === "ready") return "ready";
  return null;
}

export function isJobTerminal(job: JobStatus): boolean {
  return TERMINAL.has(job.state) || TERMINAL.has(job.stage);
}

/** The model asserted a source quote and the gate refused it. */
export function wasOverruled(record: AnswerRecord): boolean {
  return record.status === "not_stated" && record.model_claimed_found;
}

/**
 * A shared answer, with the page needed to check it.
 *
 * The document travels with the record on purpose: the point of a share link
 * is that the recipient can *verify*, not just read. A citation without its
 * source is the screenshot this product exists to replace.
 */
export interface SharedRecord {
  record_id: string;
  record: AnswerRecord;
  document: DigitisedDoc;
}
