# Upload + language detection — design

> Status: approved 26 Jul 2026. Post-sprint work. **Additive only:** `doc_a`/`doc_b`
> behaviour, their cached JSON, and the 159 existing tests must be untouched and green.

## Problem

Today the reader can only ask questions about two hardcoded documents. `cli.py::DOCUMENTS`
is both the registry and the API's allowlist, and the digitiser's `language` hint is
baked into that dict. We want: upload any page → work out what language it is → chat.

## The chicken-and-egg

Sarvam Document Digitisation has **no auto-detect**; `language` is mandatory. Detection
needs text, text needs digitisation, digitisation needs the language. We break it with a
probe pass.

## Pipeline

```
upload → validate (magic bytes, size, page count)   ← before any paid call
       → sha256 → doc_id "up_<hash16>"              ← cache hit? stop, no paid call
       → PASS 1: digitise with PROBE_LANGUAGE
       → sample ≤1000 chars from the longest body block
       → /text-lid → {language_code, script_code}
       → VERIFY against our own Unicode-block count
       → PASS 2: digitise with the resolved language (skipped iff == probe)
       → cache, recording language_source
```

### Why a verifier sits on top of LID

`/text-lid` covers **11** languages; digitisation covers **23**. LID cannot name Assamese,
Urdu, Sanskrit, Santali, Manipuri and 7 others — and will return one of its 11 rather than
admit it. So LID proposes, our deterministic Unicode-block count disposes. Same shape as
the core invariant: the model points, we check.

| Our dominant script vs LID's `script_code` | Resolution | `language_source` |
|---|---|---|
| Agree | trust LID's `language_code` | `detected` |
| Disagree, our script maps 1:1 to a language | trust **our** script, overrule LID | `script` |
| Disagree, script ambiguous (Deva, Arab) or unrecognised | do not guess — ask the reader | `user` |

Row 3 is the honest-refusal pattern applied to detection. We do not silently read an Urdu
page as Hindi.

1:1 scripts: Taml→ta-IN, Telu→te-IN, Knda→kn-IN, Mlym→ml-IN, Beng→bn-IN, Gujr→gu-IN,
Orya→od-IN, Guru→pa-IN, Olck→sat-IN, Mtei→mni-IN, Latn→en-IN.
Ambiguous: Deva (hi/mr/sa/ne/kok/mai/doi/brx), Arab (ur/ks/sd).

### ⚠️ Load-bearing assumption — Spike 0

**Does the digitiser return correctly-scripted text when the `language` hint is wrong?**
If a Tamil page probed with `hi-IN` comes back as Devanagari transliteration or noise,
there is nothing to detect from and this design collapses.

Kill it with one paid call against a throwaway `doc_id` (**never** `force=True` on
`doc_a` — that cached JSON is the offline demo fallback). If it fails, the fallback is
picker-first with LID used only to confirm afterwards: a change to one constant, because
detection is isolated behind `resolve_language()`.

## Safety note

A wrong language hint degrades **OCR quality**. It cannot produce a false citation — the
citation is still sliced from our own stored text at a verified line range. The new failure
mode is "verbatim quote of garbled text": a legibility problem, not an honesty breach.

## Boundary that must not drift

The library is a **switcher, not a corpus**. One document per conversation, always.
Switching documents starts a new conversation. No question retrieves across documents.
§6's "no multi-document RAG" stays intact.

---

## Module contracts

Agents own disjoint files. Do not edit a file you do not own.

### `askdoc/config.py` (owner: Agent C)

```python
PROBE_LANGUAGE = "hi-IN"          # Spike 0 may change this
LID_MAX_CHARS = 1000              # /text-lid hard limit
MAX_UPLOAD_BYTES = 25 * 1024 * 1024
MAX_PAGES = 10                    # the API's own per-job limit
UPLOADS_DIR = BACKEND_DIR / "uploads"
SUPPORTED_LANGUAGES: dict[str, str]   # all 23 codes → English display name
```

### `askdoc/detect.py` (owner: Agent A)

```python
SCRIPT_TO_LANGUAGE: dict[str, str]     # "Taml" -> "ta-IN"
AMBIGUOUS_SCRIPTS: frozenset[str]      # {"Deva", "Arab"}

def dominant_script(text: str) -> str
    """4-letter script code by Unicode-block frequency over letters only.
    Ignores digits, punctuation, whitespace. Returns "Zyyy" when undetermined."""

def sample_for_lid(doc: DigitisedDoc) -> str
    """≤LID_MAX_CHARS from the LONGEST block, not the first — the header of a
    bilingual government form is English and would yield en-IN for a Tamil page."""

def identify_language(text: str) -> LidResult    # POST /text-lid
    """LidResult(language_code: str|None, script_code: str|None)"""

def resolve_language(doc: DigitisedDoc, *, probe_language: str) -> Resolution
    """Resolution(language: str|None, source: str, script: str,
                  lid_language: str|None, needs_user: bool)"""
```

Reuse `AuthError`/`RateLimitError`/`ChatError` imported from `sarvam_http`; do **not**
edit `sarvam_http.py`. A LID outage is not fatal: fall back to script-only resolution.

### `askdoc/upload.py` (owner: Agent B)

```python
class UploadRejected(ValueError):
    """.message is shown verbatim to the reader."""

def sniff(head: bytes) -> str | None        # "pdf" | "png" | "jpeg" | None
def count_pdf_pages(path: Path) -> int      # pypdf
def store_upload(stream, *, filename: str) -> StoredUpload
    """Streams to a temp file with a running byte ceiling — abort mid-write, never
    buffer the whole body. Hashes while streaming. Validates, then moves to
    UPLOADS_DIR/<doc_id>.<ext>.
    StoredUpload(doc_id, path, kind, size_bytes, page_count, source_filename)"""
```

Validation order, all before any paid call:

| Check | Rule | Message |
|---|---|---|
| Magic bytes | PDF/PNG/JPEG only; extension and `Content-Type` advisory, never trusted | "I can read PDF, PNG and JPEG pages. This file looks like something else." |
| Size | streamed ceiling, `MAX_UPLOAD_BYTES` | "That file is 41 MB. I can take up to 25 MB." |
| Pages | `≤ MAX_PAGES`; images are 1 | "This PDF has 24 pages. I can read up to 10 at a time — try splitting it." |
| Readable | zero-byte, corrupt PDF | "I couldn't open this PDF — it may be damaged." |

Over-limit page counts are **rejected**, not truncated. A "not stated" that really means
"not stated in the part I read" is a different and dishonest claim.

### `askdoc/models.py` + `askdoc/cache.py` (owner: Agent C)

New `DigitisedDoc` fields — **every one needs a default** or `doc_a.json`/`doc_b.json`
stop deserialising, and those files are the offline demo fallback:

| Field | Default |
|---|---|
| `origin: Literal["builtin","upload"]` | `"builtin"` |
| `label: str` | `""` |
| `language_source: str` | `"builtin"` |
| `probe_language: str` | `""` |

Also `class StarterQuestion(Frozen): text: str; gloss: str`.

`cache._path_for` tightens to an explicit `^[a-z0-9_]+$` allowlist — `doc_id` now arrives
from a URL path instead of a hardcoded dict, so whitelist the shape rather than blacklist
attacks. Add `save_starters`/`load_starters` (`cache/<doc_id>.starters.json`).

### `askdoc/jobs.py` + `askdoc/api.py` (owner: Agent D)

```
POST /documents                     multipart → 202 {job_id}
                                    cache hit → 200 {job_id, doc_id, state:"ready"}
GET  /jobs/{job_id}                 → {state, stage, detected_language, script, doc_id?, error?}
GET  /documents                     → builtin + uploads, newest first
GET  /documents/{doc_id}            → DigitisedDoc          (DOCUMENTS allowlist dropped)
POST /documents/{doc_id}/language   {language} → 202 {job_id}
GET  /documents/{doc_id}/starters   → [StarterQuestion]
```

`stage`: `validating → digitising_probe → detecting → digitising_final → ready | failed | needs_language`.
`needs_language` is a **terminal state the UI answers with a picker**, not an error.

In-memory job registry (dict + lock). Blocking digitisation runs in a threadpool. This is
new server-side state, but the "backend stores nothing between requests" invariant is
about *session* state — history, corrections, what you asked. A job is transient plumbing
for one upload; completed documents live on disk. A restart loses in-flight uploads and
nothing else. Record this in CLAUDE.md so the invariant stays precise.

### `askdoc/starters.py` (owner: Agent E)

```python
def generate(doc: DigitisedDoc) -> tuple[StarterQuestion, ...]
```

One `sarvam-105b` call, JSON-schema output, 3–4 questions the page can actually answer.
`text` in the document's language, `gloss` in English — the frontend already renders that
shape. Generated lazily on first request, cached to disk. Failure returns `()` and the UI
shows a plain input; it must never block chat.

**Invariant check:** a suggested question is model-authored *input*, never a citation.
Every answer to one still goes through the same line-anchored gate. Pin with a test.

### Frontend (owner: Agent F)

- `components/UploadDropzone.tsx` — drag/drop + picker, client-side pre-check of the same
  rules (courtesy; the server check is the guarantee).
- `lib/useIngestionJob.ts` — 1s polling, maps `stage` to reader-facing copy:
  "Reading the page…" → "Detected Telugu" → "Re-reading in Telugu…".
- `components/LanguagePicker.tsx` — answers `needs_language`, and backs the override chip.
- Document switcher lists builtin + uploads; builtin pinned first.
- `lib/questions.ts` keeps hand-written starters for `doc_a`/`doc_b`; uploads fetch
  `/documents/{id}/starters`.
- Switching document resets the conversation.

## Error handling

| Failure | Behaviour |
|---|---|
| Invalid upload | 400, `UploadRejected.message` shown verbatim |
| Digitisation fails / `PartiallyCompleted` | job `failed` with a plain-language reason; no doc cached |
| LID unreachable | not fatal — fall back to script-only resolution |
| Script ambiguous | terminal `needs_language`, picker shown |
| Starters fail | empty list, plain input, chat unaffected |
| 429 rate limit (10 req/min) | surfaced as a retryable message, not a generic 500 |

Never report a failure to *reach* a service as "not stated" — conflating "we could not
check" with "the document does not say" is exactly the dishonesty this product prevents.

## Testing

TDD per module. No live API in tests; digitisation and LID are mocked.

- Identity: same bytes → same `doc_id`; re-upload is a cache hit with no paid call.
- Validation: each rejection rule, plus a JPEG renamed `.pdf`.
- Detection: script counting, LID agreement/disagreement/ambiguity, LID outage.
- `sample_for_lid` picks the longest block, not the first.
- `_path_for` rejects traversal and non-allowlisted shapes.
- **Compatibility: the committed `doc_a.json`/`doc_b.json` still deserialise.**
- Starters: a generated question still goes through the gate; failure degrades to `()`.
- Job state machine including `needs_language`.
- The existing 159 tests stay green.
- `python -m askdoc.evaluate` on `doc_a`/`doc_b` shows no accuracy regression.

## Scope impact

Pulls "additional languages beyond Tamil/Telugu" and (partly) "multi-page docs" off
`IDEA_SCOPE_1.md` §7. Needs an explicit rescope note there plus a new milestone. §6's
no-multi-doc-RAG and no-auth non-goals are untouched.
