# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project state

**Shipped and working.** Python backend (`backend/askdoc`, FastAPI) + Next.js frontend (`frontend`), git repo on `main`. 384 tests pass. Voice in and out. Both demo documents cached to disk.

**Latest measured run (M5, `--runs 3`): 32/36 correct, 4 irrelevant citations, zero false refusals** — see `IDEA_SCOPE_1.md` §10 for the breakdown. Quote the run, not a bare percentage: "correct", "irrelevant" and "false refusal" have different causes and different fixes, and collapsing them into one number hides the asymmetry that actually matters.

- `IDEA_SCOPE_1.md` — the control plane. Read it before proposing or making any change. It owns product scope, milestones (M0–M5), acceptance tests, non-goals, and the parking lot.
- `SOURCE_DOCS.md` — the two demo input documents (Doc A Tamil / Doc B Telugu) and their in-scope + out-of-scope demo questions.
- `SUBMISSION.md` — submission assets and the timed demo script.

⚠️ **The backend must run with `uvicorn --reload`** or prompt edits will not take effect and you will debug the wrong code.

## What this is

"Ask-the-Document": a trustworthy reader for one dense Tamil/Telugu official page (govt circular, insurance clause, exam notice, land record). It answers plain-language questions **with a verbatim source quote, or honestly says the document doesn't say so.**

Built solo under a hard time box: Sarvam Epoch Buildathon, Sun 26 Jul, build 10:30 AM–4:30 PM IST, **feature freeze 4:00 PM**, submit 4:30 PM.

## The core invariant — do not weaken this

**The citation shown to the user is always sliced out of our own copy of the digitised text. Text written by the model never becomes a citation.**

1. Digitise the page (Sarvam Vision) → digitised text, NFC-normalised once, cached.
2. Render it with **line numbers** (`lines.render_numbered`).
3. Ask `sarvam-105b` for `{answer, found, quote_from_line, quote_to_line, supporting_quote}` — the model **points at lines**, it does not retype the quote.
4. Deterministically verify the range: **in bounds, not inverted, not blank.** Width is measured and labelled, never refused — see the span-cap section below.
5. Slice those lines out of our text — that is the citation.
6. Range invalid → *"not stated in this document."*

`claim.found` is trusted in **one direction only**: a "no" is honoured immediately (refusing is the safe direction); a "yes" earns nothing until the range is verified.

### Why line-anchored, not substring-matched (changed 26 Jul, mid-sprint)

The original design had the model retype the quote and string-matched it (`gate.check_quote`). Measured on the real Tamil page, that falsely refused **~1 in 3 answerable questions** — the model paraphrased at the margins despite an explicit prompt rule naming the exact words not to substitute (`அவசியம்` → `தவறாமல்`, and a one-character `எண்` → `எண்ணை`). Prompt pressure did not close it.

Line anchoring makes paraphrase **structurally impossible** instead of detected-after-the-fact. This is a strengthening, not a relaxation.

`gate.check_quote` is still used and still fully tested — now to cross-check the model's *self-reported* quote against the lines it pointed at. A mismatch is surfaced as `model_quote_matched=False` (transparency), never as a gate; the extracted lines are shown regardless.

### ⚠️ The span cap was removed (15:10). Do not re-add it as a refusal.

There used to be a hard cap — first 8 lines, then `clamp(ceil(0.25 × total), 8, 30)` — and a citation wider than it was **refused**. Both versions shipped a bug, and the second one shipped the *same* bug the first one did: *"help me understand this notification"* was answered by the page, verified end to end, and thrown away for being too wide.

**The reasoning behind the cap was right about evidence and wrong about what to do.** "A citation that covers everything proves nothing" is true. But a wide citation is **weaker evidence, not false evidence** — and refusing destroyed a correct, fully verified answer in order to avoid an unimpressive one. That is the identical error as `gate.check_quote` (refused paraphrases) and `relevance.py` (refused on a mistranslation), both reverted for the same reason: *a check that destroys correct answers costs more than it saves.* Three times is a pattern, and the pattern is over-trusting our own gates.

Now: width is **measured and reported, never refused.** `lines.broad_above(total)` = `clamp(ceil(0.25 × total), 8, 30)` is a **label threshold**. `LineSpan` carries `line_count` and `broad`; `AnswerRecord` carries `quote_line_count` and `citation_is_broad`; the UI appends *"· 79 lines, a large part of it"* to the line label. `RefusalReason.CITATION_TOO_BROAD` is gone.

**The known cost, and it is real:** a citation spanning most of the page highlights most of the page, so the "here is exactly where this came from" signal degrades toward nothing on summary questions. The answer is still correct and the citation still verbatim; it is simply less pointed. That is a worse citation, which is the reader's to judge — it is not a reason to tell them the page is silent.

The model is still told to point at the *smallest* range that proves the answer, and told explicitly not to refuse a question because the answer is spread out. Guidance, not a gate.

### ⚠️ Refusals must be honest about WHY — this shipped broken once

`AnswerStatus` says whether the answer stands. **`RefusalReason` says why, and the distinction is not cosmetic:**

| reason | is a claim about | reader sees |
|---|---|---|
| `DOCUMENT_SILENT` | the page | "This page doesn't say." |
| `NOT_RELEVANT` | the page | "This page doesn't say." |
| `CITATION_INVALID` | **our limit** | "Couldn't verify a citation." |

The bug: an over-wide span was refused by the cap and rendered as *"This page doesn't say"* — about a page that said it plainly. **That is worse than a hallucination**, because the reader walks away believing the document lacks something it contains, and it is precisely the dishonesty this product exists to prevent.

Never collapse these into one message, in the API or the UI. Pinned by `TestRefusalsAreHonestAboutWhy`.

When touching this path, do not: soften a refusal into a hedge, fall back to a fuzzy/semantic match, let model-authored text become the citation, or add outside knowledge. A refusal that is *correct* is a feature, not a bug to fix.

**But a refusal is only correct when the page genuinely does not answer.** Every gate that refused for any *other* reason — paraphrase, judged irrelevance, excessive width — was measured and removed. Before adding a new one, ask what it does to a correct answer, and measure that, not just what it catches.

**Known limitation, be honest about it:** verification guarantees the citation is *real*, not that it is *relevant*. The model can point at genuine verbatim text that answers a different question. No string or line check can catch that — it is a retrieval problem, a separate axis.

Measured rate: **~3%** (1 miss in 36 trials). Line-anchoring largely fixed this as a side effect — under the old substring design the same question failed 3/3. Emitting a line *number* forces the model to actually locate the passage; retyping a quote can be done from memory of the gist.

### Do not re-add the relevance judge without re-measuring

An LLM-as-judge second pass (`askdoc/relevance.py`, wired via `config.RELEVANCE_CHECK`) was built and measured. It **made things worse**:

| | correct / 36 | failure mode |
|---|---|---|
| no judge | **35 (97%)** | 1 irrelevant citation |
| strict judge | 33 (92%) | 3 false refusals |
| permissive judge | 34 (94%) | 2 false refusals |

The judge mistranslated the Telugu `కోరనైనది` ("are invited") as "are NOT required" and reasoned soundly from the mistranslation into refusing a correct answer — despite an explicit "do not translate" instruction. A judge with its own error rate, biased toward refusing, destroys more correct answers than it rescues. The module is kept as a documented experiment; re-measure with `python -m askdoc.evaluate --runs 3` before enabling.

## Measuring changes

`askdoc/evalset.py` holds 12 labelled cases (7 Tamil, 5 Telugu; 8 answerable, 4 must-refuse) with hand-read ground truth. `python -m askdoc.evaluate [--runs N] [--doc doc_a]` scores three distinct outcomes — **correct**, **irrelevant** (cited real text answering something else), **false refusal** — because they have different causes and different fixes. Do not tune the prompt or the gate without running this before and after.

## Architecture

Pipeline, single document at a time, no corpus and no RAG:

```
any page (PDF/PNG/JPG) — built-in demo doc, or uploaded
  → validate before any paid call (magic bytes, size, ≤10 pages)   [upload.py]
  → Sarvam Document Digitization (async job)   ← the scored capability
  → probe pass → /text-lid → script verification → re-read  [detect.py, jobs.py]
      (built-in docs skip this: their language is known)
  → digitised text (cached to disk)
  → question or statement?  [intent.py]
  → grounded QA via sarvam-105b (JSON schema output, tool-call fallback)
  → verbatim faithfulness gate  ← the core invariant
  → answer record: question · answer · highlighted quote · "not stated" state
  → persisted to cache/records.db, shareable at /r/[recordId]   [records.py]

alongside: speak the answer or the cited line (Bulbul v3), ask out loud
(Saaras v3) — the transcript is shown, never auto-sent            [voice.py]
```

- **Citation = a highlighted verbatim text span** in the rendered digitised page, addressed by line number.

### Ingestion normalisations — applied once, before any offset is computed

Order matters; everything downstream indexes into the result.

1. **`tables.flatten_tables`** — the digitiser emits HTML tables with **one cell per line**, so a row gets split across ~6 lines and a citation lands on `<td>09</td>`: verbatim, and useless, because nothing says what the 09 counts. Each `<tr>` is rewritten as one pipe-delimited line, so a cited row reads `| | மொத்தம்: | 64 | 09 | 73 |` and proves its own arithmetic. Also cut Doc B from 125 lines to 86.
2. **NFC** — canonical Unicode composition (see `cache.build_doc`).

Both are deterministic, content-preserving normalisations of *our own* text. They do not weaken the invariant: the model still cannot author a citation.

### Uploaded documents — the language chicken-and-egg

Any PDF/PNG/JPEG page can be uploaded. Digitisation has **no auto-detect** — `language` is mandatory and there is no `auto` value — so detection needs text, text needs digitisation, and digitisation needs the language. Broken with a probe pass:

```
validate → sha256 → doc_id "up_<hash16>"   ← cache hit stops here, no paid call
        → PASS 1 digitise with config.PROBE_LANGUAGE
        → sample ≤1000 chars from the LONGEST block
        → /text-lid → {language_code, script_code}
        → verify against our own Unicode-block count
        → PASS 2 with the resolved language (skipped iff == probe)
```

**`/text-lid` proposes; our own script count disposes.** LID knows 11 languages, digitisation accepts 23, and LID answers with one of its 11 rather than admitting ignorance. So `detect.resolve_language` checks strongest-evidence-first — orthographic, then ambiguous-script, then LID agreement, then script:

| Evidence | Resolution | `language_source` |
|---|---|---|
| Distinctive letters (`ৰ`/`ৱ` → Assamese, not Bengali) | character evidence wins | `script` |
| Ambiguous script (Deva, Arab) + LID names a language actually written in it | accept LID | `detected` |
| Ambiguous script + LID names something else, or is down | **ask the reader** | `user` |
| Unambiguous script | script → language | `script` |

Character evidence outranks LID **deliberately**: LID has no Assamese and answers `bn-IN` for an Assamese page, so letting agreement win would launder a wrong answer as a corroborated one. The same check refuses Arabic + `hi-IN`, which is LID's real behaviour on an Urdu page.

**A wrong language hint degrades OCR, it cannot forge a citation** — the quote is still sliced from our own stored text at a verified line range. The new failure mode is a verbatim quote of garbled text: a legibility problem, not an honesty breach.

⚠️ **`PROBE_LANGUAGE` rests on an unmeasured assumption:** that the digitiser returns correctly-scripted text when the hint is *wrong*. If a Tamil page probed as `hi-IN` comes back as Devanagari or noise, there is nothing to detect from. Detection is isolated behind `resolve_language` so that failure costs one constant, not a redesign. **Spike this before trusting it.**

**Known limitation, be honest about it:** Manipuri is commonly written in Bengali script, so a Bengali-script Manipuri page reads as Bengali. There is no orthographic discriminator we could verify, and routing `Beng` through LID does not help — LID has no Manipuri either and answers `bn-IN`. The reader's language override is the mitigation.

**Validation runs before any paid call** (`upload.py`). Type comes from magic bytes, never the extension or the browser's `Content-Type`. Size is enforced *while streaming* with a mid-write abort, so a large upload cannot buffer into memory before being measured; `Content-Length` may refuse early but never admit. Over-limit page counts are **rejected, not truncated** — a "not stated" that means "not stated in the part I read" is a different and dishonest claim.

**The job registry is in-memory, and that does not violate "the backend stores no session state."** That invariant is about history, corrections, what you asked. A job is transient plumbing for one upload; completed documents live on disk. A restart loses in-flight uploads and nothing else. (Finished answer records *are* persisted — see "Session context" below for why that is a different thing.)

**A corrupt document file is loud, never skipped.** `GET /documents` lets the parse error propagate rather than quietly omitting the file. A document that vanishes from the list without a word is the same shape as "this page doesn't say" about a page that says it plainly — a confident false claim about absence. Pinned by `test_a_corrupt_document_is_loud_rather_than_missing`.

### One input box — question or statement

`POST /ask` returns a **discriminated union**: `AnswerRecord` (`kind: "answer"`) or `NoteAcknowledgement` (`kind: "note"`). `pipeline.handle` routes on `intent.classify`.

- **`NoteAcknowledgement` is deliberately not an `AnswerStatus`.** That enum describes what the *document* says and has exactly two states. "Noted" is not a claim about the document, so it is a separate kind of turn — which keeps the two-state guarantee as narrow as it should be.
- **The classifier is biased toward answering.** Misreading a question as a statement swallows it silently (the reader is told "noted" and never learns the page had an answer); misreading a statement as a question yields a *visible* refusal they can recover from. Every uncertain and failing path returns "question" — including classifier outage and malformed output. Do not invert this.
- **Fast path:** a message ending in `?` skips the classifier entirely, so the common case stays at one model call.

### Session context — multi-turn and corrections

`AskRequest` carries `history` and `corrections`; **the backend stores no session state between requests.** Reloading is therefore a complete, reliable reset (this matters for M5).

⚠️ **Say "session state", not "nothing" — that stopped being true when share links shipped.** `records.py` writes **every** answer to `cache/records.db` (SQLite, stdlib), refusals included, on every `/ask`. What is persisted is the finished *artifact* — question, answer, verified line range — never the conversation. History and corrections remain client-held and are never written anywhere. The distinction is the whole point: an answer record is designed to outlive the session and be re-checked from a link; a conversation is not. Two other things follow from it, and both are load-bearing:

- **`records.db` must never be committed.** It accumulates questions asked about other people's uploaded paperwork. Ignored in the root `.gitignore`.
- **The in-memory job registry is still session-shaped plumbing**, not storage: it holds one upload in flight, and a restart loses only in-flight uploads.

⚠️ **What "reload resets" means changed with the route split.** The UI is three routes: `/` (library + upload), `/doc/[docId]` (reader) and `/r/[recordId]` (a shared answer record, re-checked against the document when the link opens). Reloading the reader keeps the *document* — it is addressable, not stateful — and still drops history and corrections. `lib/useConversation.ts` holds them in plain `useState` with **no persistence layer at all**; the retired `localStorage` conversation store was deleted, not merely unread, because persisted chats and "reload is a complete reset" cannot both be true. Resuming an old chat is gone with it; closing the tab loses the thread.

**Switching documents resets the conversation structurally, not by hand.** Two documents are two routes that never share a store. Note that Next reuses the reader component when only the param changes, so `useConversation` resets *during render* on `docId` change — an effect would paint one frame of doc A's answers against doc B's text. Re-digitising keeps the same id, so it calls `reload()` + `startOver()` explicitly: a new reading has new line numbers, and old citations would point nowhere.

- **History is replayed as a real multi-turn conversation** — alternating `user`/`assistant` messages via `prompts.build_messages`, not flattened into prose inside one user turn. Assistant turns are reconstructed from the *verified* record, so a refusal replays as `found: false`.
- ⚠️ **The follow-up rule is conditional on `history` being non-empty.** Including it on first-turn questions cost **8 points of accuracy** (96% → 88%). Rules about a conversation that isn't happening dilute the ones that matter. Two tests pin this.
- **Corrections ride on the system message.** They can change *which* lines get cited; they can never become a citation. Pinned by `test_a_correction_is_never_quoted`.
- ⚠️ **Do not re-fence the notes block with negatives.** It originally opened with three ("NOT part of the document", "never point at them", "never let a note alone be your answer") and the model discounted notes entirely — it kept asking the reader to repeat what they had already said. Assert the notes as TRUE first, then state the single citation limit. Pinned by `TestNotesAreFramedToBeUsed`.
- ⚠️ **A refusal recorded before a note existed is dropped from history** when corrections are present. Replaying it anchored the model into repeating the refusal even though the note now supplied what was missing — 3/3, and explicit prompt instruction did not move it. Cited turns are kept: a real citation does not go stale.

**What corrections are actually for.** Glossary-style notes ("X means Y") have no headroom — sarvam-105b already bridges English↔Tamil terms and even reads through OCR errors (`అంగస్ వాడి` for `అంగన్‌వాడీ`), verified. What works is context the model **cannot infer**: the reader's own situation. "I'm applying to the Maldakal project" turns *"how many vacancies in my project?"* from a correct refusal into a cited answer on line 17. Note the refusal without the note is right, not a bug — the note supplies the missing **referent**, never the answer.

- **Cache the digitised output of both demo docs to disk.** This is the offline fallback for a dead API during the demo, and it makes iteration fast (digitisation is the slow, paid step — don't re-run it on every code change). `doc_a.json`/`doc_b.json` are **committed**; uploads, starters and `records.db` are not.
- The final artifact is an **answer record** (shareable, verifiable), not a chat log.

### Voice — the invariant in a channel that has no line numbers

Shipped 14:55 as an explicit rescope of §7. Two decisions carry it:

**1. A transcript is never auto-sent.** `POST /transcribe` returns `{transcript}` and *nothing else*; `useVoiceInput` puts it in the input box and stops. A misheard question would otherwise produce a **fully verified citation answering something the reader never asked** — correct by every check we run, every signal on screen reading "verified", and still wrong. This is the same class of failure as the ~3% irrelevant-citation rate, except self-inflicted. Making the words visible first turns a silent failure into an obvious one. Pinned by `test_nothing_is_answered_only_transcribed`.

Confirmed real, not theoretical: a TTS→STT round-trip of `தேர்வின் கால அளவு எவ்வளவு?` came back as `தேவின்` — one character dropped. That is the design working, not a bug to fix.

**2. The citation is spoken by offset, never by text.** `POST /speak` with `source: "quote"` takes `quote_start`/`quote_end` and re-slices from `doc.text`; only `source: "answer"` accepts a string, and an answer was always model-authored prose. Audio has no visual distinction between the page's words and the model's, so the guarantee has to hold here for the same reason it holds on screen. Pinned by `TestTheDocumentCannotBeMisquotedAloud` — including a caller that sends both valid offsets *and* a forged `text`, and gets the document.

The UI shows **two separate labelled buttons** ("The answer" / "The page"), never one. Heard rather than seen, they are indistinguishable, and the reader knowing which is which is the entire product.

Refusals have no audio: that copy is in English, not the document's language, and there is no citation to read.


- `STT_MODE = "transcribe"`, not `"translate"` — the question must reach the model in the language the page is written in.
- `language_code` is the **document's** language, not `"unknown"`. We know which page is open; telling the recogniser beats making it guess.
- Saaras accepts `webm`/`opus`/`m4a` directly, so `MediaRecorder` output is **not transcoded**.
- `TTS_SPEAKER = "shreya"` (calm narration) is editorial: the roster's warm product/IVR and young-energetic voices would lend an official page a tone it does not have.
- Audio is generated **per click and never prefetched** — it is a paid call and most answers are read, not heard. Clips are cached client-side so replay is free.

## Verified Sarvam API facts

Checked against docs.sarvam.ai. Where these conflict with `IDEA_SCOPE_1.md` §1a, **these win** — see "Corrections" below.

**Auth:** base URL `https://api.sarvam.ai`; header `api-subscription-key: <key>` (Bearer also accepted). Read the key from `SARVAM_API_KEY` env — never hardcode it. Auth failures return **403** (not 401) with `error.code: invalid_api_key_error`; 429 = rate limit/quota.

**Digitisation** — async job, five steps via the Python SDK:

```python
from sarvamai import SarvamAI
client = SarvamAI(api_subscription_key=os.environ["SARVAM_API_KEY"])

job = client.document_intelligence.create_job(language="ta-IN", output_format="md")
job.upload_file("doc_a.pdf")
job.start()
status = job.wait_until_complete(timeout=300)   # Python SDK waits forever without an explicit timeout
job.download_output("output.zip")
```

- `language` (not `language_code`): `ta-IN` Tamil, `te-IN` Telugu. **Default is `hi-IN` — you must set it.**
- `output_format`: `"md"` | `"html"` | `"json"`. Use `"md"`, not `"markdown"` (400). **JSON page-level data is always in the ZIP regardless**; `"json"` returns *only* the JSON, dropping the md/html. Prefer `"md"` — you get renderable Markdown for the highlight UI *and* the JSON.
- Limits: PDF ≤10 pages, PNG/JPEG single image, ZIP ≤10 flat images; **≤200 MB**.
- Job states: `Accepted` → `Pending` → `Running` → `Completed` | `PartiallyCompleted` | `Failed`. Handle `PartiallyCompleted` — it is not success.

**Grounded QA** — `POST /v1/chat/completions`:

- Models: **`sarvam-105b`** (the one to use — see the verified-live table below; `sarvam-30b` cannot hold structured output and serves only as a forced-tool-call fallback). `sarvam-m` is **deprecated** and now errors.
- `temperature=0.0` + fixed `seed`. Note `seed` is best-effort, **not guaranteed** — do not stake demo repeatability on it; stake it on the cached digitised text.
- `response_format` = `{"type": "json_schema", "json_schema": {"name": ..., "schema": ..., "strict": true}}` to force `{answer, supporting_quote, found}`.
- **Set `reasoning_effort=None` and keep `max_tokens` generous.** Reasoning is on by default (`sarvam-105b` defaults to `"low"`), and reasoning tokens can consume the whole budget, returning empty structured output. This is the most likely silent failure in the QA step.
- **Do not pass `wiki_grounding`** — no longer supported on `sarvam-30b`/`sarvam-105b`. Groundedness comes from the prompt plus line-anchored extraction, not from this flag.

## Corrections to IDEA_SCOPE_1.md §1a

That section was written pre-sprint and has drifted. Verified against live docs:

| Scope doc says | Actually |
|---|---|
| Pass `wiki_grounding: false` | Silently **accepted** (HTTP 200), not an error. Still omit it — it does nothing for us |
| 6-step REST dance (`get-upload-links`, `get-download-links`) | SDK collapses to **5 calls** (`create_job`/`upload_file`/`start`/`wait_until_complete`/`download_output`) — the "riskiest dependency" is much smaller than M0 assumes |
| ≤50 MB | **≤200 MB** |
| ≤10 pages per *project* | ≤10 pages per **job** |
| `output_format: "json"` preferred | Neither. Pass `"md"` (the SDK default is `"html"`), but **read the page JSON out of the ZIP** — see below |
| `seed` gives repeatable demos | Not honoured at all; identical `temperature=0, seed=42` gave different output. Repeatability comes from the cached digitised text |

### Verified live on 26 Jul — these override §1a and the table above

| Claim | Reality |
|---|---|
| Use `sarvam-30b` for QA | **Unusable for structured output.** 1 of 21 calls returned parseable JSON; it emits a valid prefix then degenerates into whitespace until `finish_reason: "length"`. `strict: true` does not help. **Use `sarvam-105b`** (21/21) |
| `response_format` via the SDK | `sarvamai` 0.1.28's `chat.completions()` has **no `response_format` param**. Chat goes over raw HTTP (`askdoc/sarvam_http.py`); digitisation keeps the SDK |
| Bounding boxes are not in the API | **False.** `metadata/page_NNN.json` in the ZIP returns `coordinates {x1,y1,x2,y2}` per block, plus `layout_tag`, `confidence`, `reading_order`. Stored in `models.Block`; **not rendered** — visual pins remain a §7 parking-lot item |
| — | **ZIP contents:** `document.md` + `metadata/page_NNN.json` |
| — | **Use the JSON blocks, not `document.md`.** The Markdown renumbers every wrapped line as a fresh list item, injecting markers like `26. ` *into the middle of sentences* and making verbatim quotes unmatchable. The JSON preserves the page's own numbering |
| — | **Models translate quotes to English by default.** Needs an explicit "ORIGINAL SCRIPT, never translate" rule in the prompt *and* on the schema property |
| — | `json_object` mode returns *valid JSON that silently omits required fields*. Validate with a schema (pydantic), never just `json.loads` |
| — | Digitisation rate limit **10 req/min**; chat 40–120 req/min by plan |
| — | No credits/quota endpoint exists (`/v1/credits`, `/usage`, `/me` all 404). Check the dashboard |
| — | `GET /v1/models` lists exactly `sarvam-105b`, `sarvam-30b`. `sarvam-m` → 400 deprecated (SDK type hints still list it) |
| — | python.org macOS Python does **not** trust the system keychain — `urllib` fails `CERTIFICATE_VERIFY_FAILED`. Use `httpx` (bundles certifi) |

⚠️ **Security:** `inspect.signature(SarvamAI.__init__)` renders the live API key inline — its default is `os.getenv("SARVAM_API_KEY")` evaluated at import. Never log or print that signature. Rotate the key if a transcript containing it leaves the machine.

Unverified (re-check at the dashboard before relying on them): ₹100 free credits, ₹0.5/page digitisation.

## Commands

```bash
export SARVAM_API_KEY="..."      # from dashboard.sarvam.ai; shown once at creation

# --- backend (Python 3.12 venv via uv) ---
cd backend
uv venv --python 3.12 && uv pip install -U sarvamai fastapi "uvicorn[standard]" pytest pytest-cov python-multipart pypdf
.venv/bin/python -m pytest                          # 384 tests
.venv/bin/python -m pytest --cov=askdoc --cov-report=term-missing

# Run the API. ALWAYS pass --reload in dev: without it uvicorn holds the module
# it imported at boot, so new routes never appear and a POST to an existing
# path returns 405 Method Not Allowed while the tests stay green -- TestClient
# imports fresh from disk, so it never sees the stale process.
.venv/bin/python -m uvicorn askdoc.api:app --port 8000 --host 127.0.0.1 --reload

.venv/bin/python -m askdoc.cli digitise --doc doc_a # cached; --force re-runs the PAID call
.venv/bin/python -m askdoc.cli show     --doc doc_a # print cached digitised text
.venv/bin/python -m askdoc.cli ask      --doc doc_a "question" ["question2" ...]

# --- HTTP API ---
# POST /documents                    multipart, field "file" -> 202 {job_id}
#                                    cache hit -> 200 {job_id, doc_id, state:"ready"}
# GET  /jobs/{job_id}                state is authoritative; doc_id ALWAYS present
# GET  /documents                    full DigitisedDoc incl. text, newest first
# GET  /documents/{doc_id}           |  POST /documents/{doc_id}/language {"language"}
# GET  /documents/{doc_id}/starters  generated once, [] is a valid 200
# POST /ask                          AnswerRecord | NoteAcknowledgement (kind:)
#                                    every answer is saved; id on X-Record-Id
# GET  /records/{record_id}          shared answer + its document, re-checked
# POST /transcribe                   returns {transcript} ONLY — never answers
# POST /speak                        source:"quote" re-slices by offset;
#                                    source:"answer" is the only one taking text

# --- frontend (Next.js 16, TS, Tailwind) ---
# /              library + upload (ingestion waits here; failures handled here)
# /doc/[docId]   reader — one document, always
# /r/[recordId]  a shared answer record
cd frontend && npm run dev                          # expects backend at NEXT_PUBLIC_API_BASE
```

Docs are `doc_a` (Tamil) and `doc_b` (Telugu); see `askdoc/cli.py::DOCUMENTS`.

## Working rules for this repo

- **`IDEA_SCOPE_1.md` is authoritative on scope.** Its §6 non-goals and §7 parking lot are binding: no voice/telephony, no multi-doc RAG, no legal/financial advice, no bbox pins, no translation, no auth/accounts. Do not pull a parking-lot item onto the critical path without an explicit rescope.
- **Milestone order is fixed (M0→M5); when behind, take the milestone's stated fallback rather than reordering.** M5 (demo hardening) is protected — never skip it to add features.
- **No UI until the M1 console slice prints a correct, verified quote on the real demo page.** This is the explicit gate in §3.
- Prefer working end-to-end over complete. An ugly vertical slice that passes the gate beats a polished component that doesn't.
- Update the §10 status tracker in `IDEA_SCOPE_1.md` as milestones pass.
- Language note: Tamil/Telugu counts toward the Sarvam parameter and asymmetric fit, **not** Creativity — the rubric excludes language swaps from Creativity. Keep those claims separate.
