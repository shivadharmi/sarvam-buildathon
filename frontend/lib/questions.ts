/**
 * Starter questions per document, with English glosses.
 *
 * The glosses are not decoration: most people looking at this cannot read
 * Tamil or Telugu, and without them the refusal beat is invisible -- you
 * cannot tell a correct refusal from a broken app if you can't read either.
 *
 * Each set deliberately ends with a question the page does NOT answer.
 *
 * The two demo documents keep their hand-written sets: they were read by hand
 * and their unanswerable and needs-a-note cases are known-true, which is not
 * something a generator can promise. Uploads fetch generated ones instead.
 */

import { getStarters } from "./api";
import { languageName } from "./languages";
import type { DigitisedDoc } from "./types";

export interface StarterQuestion {
  text: string;
  gloss: string;
  /** True when the page genuinely does not answer this. */
  unanswerable?: boolean;
  /** True when the page can only answer this once the reader adds a note. */
  needsNote?: boolean;
}

export interface StarterNote {
  note: string;
  gloss: string;
}

/**
 * Suggested notes, offered one click away.
 *
 * Only listed where the effect was actually verified. Doc A has none: several
 * candidates were tried and the page refused with and without them, which is
 * the correct behaviour but makes for a suggestion that does nothing.
 */
export const STARTER_NOTES: Record<string, StarterNote[]> = {
  doc_b: [
    {
      note: "నేను మల్దకల్ ప్రాజెక్టుకు దరఖాస్తు చేస్తున్నాను.",
      gloss: "I'm applying to the Maldakal project",
    },
  ],
};

export const STARTER_QUESTIONS: Record<string, StarterQuestion[]> = {
  doc_a: [
    {
      text: "இந்த வினாத்தொகுப்பில் எத்தனை வினாக்கள் உள்ளன?",
      gloss: "How many questions are in this booklet?",
    },
    {
      text: "விடைத்தாளை நிரப்ப எந்த வகையான பேனாவைப் பயன்படுத்த வேண்டும்?",
      gloss: "What kind of pen must I use on the answer sheet?",
    },
    {
      text: "வினாத்தொகுப்பு எண்ணை எழுதாவிட்டால் என்ன ஆகும்?",
      gloss: "What happens if I don't write the booklet number?",
    },
    {
      text: "இந்தத் தேர்வில் தேர்ச்சி பெற எத்தனை மதிப்பெண்கள் தேவை?",
      gloss: "What marks are needed to pass this exam?",
      unanswerable: true,
    },
  ],
  doc_b: [
    {
      text: "దరఖాస్తు చేసుకోవడానికి చివరి తేదీ ఎప్పుడు?",
      gloss: "What is the last date to apply?",
    },
    {
      text: "అభ్యర్థుల వయస్సు ఎంత ఉండాలి?",
      gloss: "What must the candidate's age be?",
    },
    {
      text: "విద్యార్హత ఏమిటి?",
      gloss: "What is the educational qualification?",
    },
    {
      text: "నా ప్రాజెక్టులో ఎన్ని ఖాళీలు ఉన్నాయి?",
      gloss: "How many vacancies in my project?",
      needsNote: true,
    },
    {
      text: "దరఖాస్తు రుసుము ఎంత?",
      gloss: "What is the application fee?",
      unanswerable: true,
    },
  ],
};

export const DOCUMENT_LABELS: Record<string, { name: string; script: string }> = {
  doc_a: { name: "TNPSC Group IV exam booklet", script: "Tamil" },
  doc_b: { name: "Anganwadi recruitment notice", script: "Telugu" },
};

const CHIP_LENGTH = 16;

/** Drop the extension: ".pdf" on a chip says nothing the reader needs. */
function withoutExtension(filename: string): string {
  return filename.replace(/\.[a-z0-9]+$/i, "");
}

/**
 * The short name on a switcher chip.
 *
 * An upload is named by the file the reader handed over — two Tamil pages must
 * be told apart, and "Tamil" twice cannot do that.
 */
export function shortLabel(doc: DigitisedDoc): string {
  const builtin = DOCUMENT_LABELS[doc.doc_id];
  if (builtin) return builtin.script;

  const named = withoutExtension(doc.label || doc.source_filename || "").trim();
  if (!named) return languageName(doc.language);
  return named.length > CHIP_LENGTH ? `${named.slice(0, CHIP_LENGTH)}…` : named;
}

/** The full name, for the document header and chip tooltips. */
export function fullName(doc: DigitisedDoc): string {
  return (
    DOCUMENT_LABELS[doc.doc_id]?.name || doc.label || doc.source_filename || doc.doc_id
  );
}

/**
 * Starters for a document: hand-written for the demo pages, generated for
 * uploads.
 *
 * A failure here is never surfaced. Starters are a convenience — the input box
 * works without them, and an error where a suggestion should be would read as
 * the page itself being broken.
 */
export async function loadStarters(docId: string): Promise<StarterQuestion[]> {
  const handWritten = STARTER_QUESTIONS[docId];
  if (handWritten) return handWritten;

  try {
    const generated = await getStarters(docId);
    return generated.map((starter) => ({ text: starter.text, gloss: starter.gloss }));
  } catch {
    return [];
  }
}
