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
export type RefusalReason =
  | "document_silent"
  | "citation_too_broad"
  | "citation_invalid"
  | "not_relevant";

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

  model: string;
  asked_at: string;

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

export interface DigitisedDoc {
  doc_id: string;
  language: string;
  /** NFC-normalised. Quote offsets index into this exact string. */
  text: string;
  source_filename: string;
  digitised_at: string;
  page_count: number;
}

/** The model asserted a source quote and the gate refused it. */
export function wasOverruled(record: AnswerRecord): boolean {
  return record.status === "not_stated" && record.model_claimed_found;
}
