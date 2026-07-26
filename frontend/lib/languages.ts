/**
 * The 23 languages Sarvam Document Digitisation can read.
 *
 * Mirrors backend/askdoc/config.py::SUPPORTED_LANGUAGES. Kept on the client as
 * well because the picker has to be drawn before the backend has any opinion
 * about the file — that is the whole point of the picker.
 *
 * Names are in English on purpose. The picker exists precisely when we could
 * not work out what the reader reads, so labelling it in a script we only
 * guessed at would be asking the question in the answer.
 */
export const SUPPORTED_LANGUAGES: Record<string, string> = {
  "as-IN": "Assamese",
  "bn-IN": "Bengali",
  "brx-IN": "Bodo",
  "doi-IN": "Dogri",
  "en-IN": "English",
  "gu-IN": "Gujarati",
  "hi-IN": "Hindi",
  "kn-IN": "Kannada",
  "ks-IN": "Kashmiri",
  "kok-IN": "Konkani",
  "mai-IN": "Maithili",
  "ml-IN": "Malayalam",
  "mni-IN": "Manipuri",
  "mr-IN": "Marathi",
  "ne-IN": "Nepali",
  "od-IN": "Odia",
  "pa-IN": "Punjabi",
  "sa-IN": "Sanskrit",
  "sat-IN": "Santali",
  "sd-IN": "Sindhi",
  "ta-IN": "Tamil",
  "te-IN": "Telugu",
  "ur-IN": "Urdu",
};

/** Alphabetical by English name — a list of 23 is only usable if it is predictable. */
export const LANGUAGE_OPTIONS: { code: string; name: string }[] = Object.entries(
  SUPPORTED_LANGUAGES,
)
  .map(([code, name]) => ({ code, name }))
  .sort((a, b) => a.name.localeCompare(b.name));

/**
 * The English name, or the raw code when the backend names one we do not know.
 *
 * Never returns a blank: a status line reading "Re-reading in …" would tell the
 * reader we are doing something without saying what.
 */
export function languageName(code: string | null | undefined): string {
  if (!code) return "the page language";
  return SUPPORTED_LANGUAGES[code] ?? code;
}

/**
 * Placeholder for the question box, in the language of the page.
 *
 * Only the two scripts this project has actually verified are written out. For
 * everything else the placeholder stays in English rather than shipping a
 * machine-guessed phrase into a script nobody here can proofread.
 */
export function askPlaceholder(language: string | null | undefined): string {
  if (language === "ta-IN") return "உங்கள் கேள்வி…";
  if (language === "te-IN") return "మీ ప్రశ్న…";
  return "Your question…";
}
