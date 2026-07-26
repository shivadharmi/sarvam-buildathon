"""Environment and constants. Fails fast when required secrets are absent."""

from __future__ import annotations

import os
from pathlib import Path

# --- paths -------------------------------------------------------------------

BACKEND_DIR = Path(__file__).resolve().parent.parent
REPO_DIR = BACKEND_DIR.parent
DOCS_DIR = REPO_DIR / "docs"
CACHE_DIR = BACKEND_DIR / "cache"

# Original bytes of uploaded documents, kept so a language override can
# re-digitise without asking the reader for the file a second time.
UPLOADS_DIR = BACKEND_DIR / "uploads"

# --- Sarvam API --------------------------------------------------------------

API_KEY_ENV = "SARVAM_API_KEY"

# Verified live on 26 Jul: sarvam-105b honours response_format json_schema
# (valid JSON in ~40 tokens). sarvam-30b does NOT -- it degenerates and burns
# the whole token budget -- but it does honour forced tool calls, which is why
# it serves as the fallback strategy rather than being dropped.
QA_MODEL = "sarvam-105b"
QA_FALLBACK_MODEL = "sarvam-30b"

# Reasoning is ON by default (sarvam-105b defaults to "low") and its tokens can
# consume the whole budget, returning empty structured output. Disable it and
# keep the budget generous.
QA_REASONING_EFFORT = None
QA_MAX_TOKENS = 2048
QA_TEMPERATURE = 0.0
QA_SEED = 42  # best-effort only; repeatability comes from the digitised cache

# Second pass asking whether the cited passage actually answers the question.
#
# OFF, and this is a measured decision, not an omission. Over 36 trials on the
# labelled set in `evalset.py`:
#
#   no relevance check        35/36 (97%)   1 irrelevant citation
#   strict judge              33/36 (92%)   3 false refusals
#   permissive judge          34/36 (94%)   2 false refusals
#
# The judge has its own error rate and it exceeds the problem it fixes. It
# repeatedly rendered the Telugu "కోరనైనది" ("are invited") as "are NOT
# required" and then reasoned soundly from the mistranslation into a refusal --
# despite being told explicitly not to translate. An inaccurate judge biased
# toward refusing destroys more correct answers than it rescues.
#
# Keep the module: it is a documented experiment, and it may pay off with a
# better judge model or on longer documents where retrieval is harder.
# Re-measure with `python -m askdoc.evaluate --runs 3` before turning it on.
RELEVANCE_CHECK = False

DIGITISE_OUTPUT_FORMAT = "md"  # "markdown" is rejected with 400
DIGITISE_TIMEOUT_S = 300  # the SDK waits forever without an explicit timeout

LANGUAGES = {"ta": "ta-IN", "te": "te-IN"}  # default is hi-IN; always set it

# --- upload ingestion --------------------------------------------------------

# Digitisation has no auto-detect: `language` is mandatory and there is no
# "auto" value. So detection needs text, text needs digitisation, and
# digitisation needs the language. We break the cycle with a probe pass, read
# the script off what comes back, and re-digitise only when the guess was wrong.
#
# ⚠️ This constant rests on an assumption that must be measured, not assumed:
# that the digitiser returns correctly-scripted text when the hint is WRONG.
# If a Tamil page probed as hi-IN comes back as Devanagari or noise, there is
# nothing to detect from. Detection is isolated behind `detect.resolve_language`
# precisely so that failure costs one constant, not a redesign.
PROBE_LANGUAGE = "hi-IN"

LID_MAX_CHARS = 1000  # /text-lid rejects longer input
MAX_UPLOAD_BYTES = 25 * 1024 * 1024  # the API allows 200 MB; a dense scan is 1-3 MB
MAX_PAGES = 10  # the API's own per-job hard limit

# Every language digitisation accepts. Note /text-lid only knows 11 of these --
# which is exactly why LID's verdict is checked against the script we can see
# for ourselves rather than trusted outright.
SUPPORTED_LANGUAGES = {
    "as-IN": "Assamese",
    "bn-IN": "Bengali",
    "brx-IN": "Bodo",
    "doi-IN": "Dogri",
    "en-IN": "English",
    "gu-IN": "Gujarati",
    "hi-IN": "Hindi",
    "kn-IN": "Kannada",
    "kok-IN": "Konkani",
    "ks-IN": "Kashmiri",
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
}

# --- product copy ------------------------------------------------------------

NOT_STATED = "not stated in this document"

# What the reader is told for each way an answer can fail to stand.
#
# Only DOCUMENT_SILENT is a claim about the page. The others are limits of
# ours, and wording them as silence would tell the reader the page lacks
# something it actually contains -- the exact dishonesty this product exists
# to prevent. Keep these distinct.
TOO_BROAD = "the answer spans more of this page than can be quoted at once"
UNVERIFIED = "could not verify a citation for this on the page"


def api_key() -> str:
    """Return the Sarvam API key, or raise with an actionable message."""
    key = os.environ.get(API_KEY_ENV, "").strip()
    if not key:
        raise RuntimeError(
            f"{API_KEY_ENV} is not set. Create a key at dashboard.sarvam.ai "
            f"and run: export {API_KEY_ENV}=..."
        )
    return key
