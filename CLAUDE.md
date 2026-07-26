# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project state

**There is no source code yet.** The repo currently contains two planning docs and nothing else. It is not a git repository.

- `IDEA_SCOPE_1.md` — the control plane. Read it before proposing or making any change. It owns product scope, milestones (M0–M5), acceptance tests, non-goals, and the parking lot.
- `SOURCE_DOCS.md` — the two demo input documents (Doc A Tamil / Doc B Telugu) and their in-scope + out-of-scope demo questions.

**Update the "Commands" section below the moment a scaffold lands.** Do not let it stay aspirational.

## What this is

"Ask-the-Document": a trustworthy reader for one dense Tamil/Telugu official page (govt circular, insurance clause, exam notice, land record). It answers plain-language questions **with a verbatim source quote, or honestly says the document doesn't say so.**

Built solo under a hard time box: Sarvam Epoch Buildathon, Sun 26 Jul, build 10:30 AM–4:30 PM IST, **feature freeze 4:00 PM**, submit 4:30 PM.

## The core invariant — do not weaken this

**The citation shown to the user is always sliced out of our own copy of the digitised text. Text written by the model never becomes a citation.**

1. Digitise the page (Sarvam Vision) → digitised text, NFC-normalised once, cached.
2. Render it with **line numbers** (`lines.render_numbered`).
3. Ask `sarvam-105b` for `{answer, found, quote_from_line, quote_to_line, supporting_quote}` — the model **points at lines**, it does not retype the quote.
4. Deterministically verify the range: in bounds, not inverted, not blank, **≤ 8 lines** (`lines.MAX_QUOTE_LINES`).
5. Slice those lines out of our text — that is the citation.
6. Range invalid → *"not stated in this document."*

`claim.found` is trusted in **one direction only**: a "no" is honoured immediately (refusing is the safe direction); a "yes" earns nothing until the range is verified.

### Why line-anchored, not substring-matched (changed 26 Jul, mid-sprint)

The original design had the model retype the quote and string-matched it (`gate.check_quote`). Measured on the real Tamil page, that falsely refused **~1 in 3 answerable questions** — the model paraphrased at the margins despite an explicit prompt rule naming the exact words not to substitute (`அவசியம்` → `தவறாமல்`, and a one-character `எண்` → `எண்ணை`). Prompt pressure did not close it.

Line anchoring makes paraphrase **structurally impossible** instead of detected-after-the-fact. This is a strengthening, not a relaxation.

`gate.check_quote` is still used and still fully tested — now to cross-check the model's *self-reported* quote against the lines it pointed at. A mismatch is surfaced as `model_quote_matched=False` (transparency), never as a gate; the extracted lines are shown regardless.

**The span cap is load-bearing.** Without it the model could point at the whole document — verbatim, passing every check, proving nothing.

It is **proportional**, not fixed: `lines.max_quote_lines` = `clamp(ceil(0.25 × total_lines), 8, 30)`. A flat 8 was a crude proxy for "a part of the page, not the page", and it refused a legitimate 15-line answer to *"help me understand this notification"* — probably the most common thing a real reader asks of a dense official page. A quarter of the page is still unmistakably a part of it, and citing everything remains impossible at any document length.

### ⚠️ Refusals must be honest about WHY — this shipped broken once

`AnswerStatus` says whether the answer stands. **`RefusalReason` says why, and the distinction is not cosmetic:**

| reason | is a claim about | reader sees |
|---|---|---|
| `DOCUMENT_SILENT` | the page | "This page doesn't say." |
| `NOT_RELEVANT` | the page | "This page doesn't say." |
| `CITATION_TOO_BROAD` | **our limit** | "Too much of the page to quote." + how to narrow |
| `CITATION_INVALID` | **our limit** | "Couldn't verify a citation." |

The bug: an over-wide span was refused by the cap and rendered as *"This page doesn't say"* — about a page that said it plainly. **That is worse than a hallucination**, because the reader walks away believing the document lacks something it contains, and it is precisely the dishonesty this product exists to prevent.

Never collapse these into one message, in the API or the UI. Pinned by `TestRefusalsAreHonestAboutWhy`.

When touching this path, do not: soften a refusal into a hedge, fall back to a fuzzy/semantic match, let model-authored text become the citation, remove the span cap, or add outside knowledge. A refusal that is *correct* is a feature, not a bug to fix.

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
Tamil/Telugu page (PDF/PNG/JPG)
  → Sarvam Document Digitization (async job)   ← the scored capability
  → digitised text (cached to disk)
  → grounded QA via sarvam-30b (JSON schema output)
  → verbatim faithfulness gate  ← the core invariant
  → answer record: question · answer · highlighted quote · "not stated" state
```

- **Citation = a highlighted verbatim text span** in the rendered digitised page, addressed by line number.

### Ingestion normalisations — applied once, before any offset is computed

Order matters; everything downstream indexes into the result.

1. **`tables.flatten_tables`** — the digitiser emits HTML tables with **one cell per line**, so a row gets split across ~6 lines and a citation lands on `<td>09</td>`: verbatim, and useless, because nothing says what the 09 counts. Each `<tr>` is rewritten as one pipe-delimited line, so a cited row reads `| | மொத்தம்: | 64 | 09 | 73 |` and proves its own arithmetic. Also cut Doc B from 125 lines to 86.
2. **NFC** — canonical Unicode composition (see `cache.build_doc`).

Both are deterministic, content-preserving normalisations of *our own* text. They do not weaken the invariant: the model still cannot author a citation.

### One input box — question or statement

`POST /ask` returns a **discriminated union**: `AnswerRecord` (`kind: "answer"`) or `NoteAcknowledgement` (`kind: "note"`). `pipeline.handle` routes on `intent.classify`.

- **`NoteAcknowledgement` is deliberately not an `AnswerStatus`.** That enum describes what the *document* says and has exactly two states. "Noted" is not a claim about the document, so it is a separate kind of turn — which keeps the two-state guarantee as narrow as it should be.
- **The classifier is biased toward answering.** Misreading a question as a statement swallows it silently (the reader is told "noted" and never learns the page had an answer); misreading a statement as a question yields a *visible* refusal they can recover from. Every uncertain and failing path returns "question" — including classifier outage and malformed output. Do not invert this.
- **Fast path:** a message ending in `?` skips the classifier entirely, so the common case stays at one model call.

### Session context — multi-turn and corrections

`AskRequest` carries `history` and `corrections`; **the backend stores nothing between requests.** Reloading the page is therefore a complete, reliable reset (this matters for M5).

- **History is replayed as a real multi-turn conversation** — alternating `user`/`assistant` messages via `prompts.build_messages`, not flattened into prose inside one user turn. Assistant turns are reconstructed from the *verified* record, so a refusal replays as `found: false`.
- ⚠️ **The follow-up rule is conditional on `history` being non-empty.** Including it on first-turn questions cost **8 points of accuracy** (96% → 88%). Rules about a conversation that isn't happening dilute the ones that matter. Two tests pin this.
- **Corrections ride on the system message.** They can change *which* lines get cited; they can never become a citation. Pinned by `test_a_correction_is_never_quoted`.
- ⚠️ **Do not re-fence the notes block with negatives.** It originally opened with three ("NOT part of the document", "never point at them", "never let a note alone be your answer") and the model discounted notes entirely — it kept asking the reader to repeat what they had already said. Assert the notes as TRUE first, then state the single citation limit. Pinned by `TestNotesAreFramedToBeUsed`.
- ⚠️ **A refusal recorded before a note existed is dropped from history** when corrections are present. Replaying it anchored the model into repeating the refusal even though the note now supplied what was missing — 3/3, and explicit prompt instruction did not move it. Cited turns are kept: a real citation does not go stale.

**What corrections are actually for.** Glossary-style notes ("X means Y") have no headroom — sarvam-105b already bridges English↔Tamil terms and even reads through OCR errors (`అంగస్ వాడి` for `అంగన్‌వాడీ`), verified. What works is context the model **cannot infer**: the reader's own situation. "I'm applying to the Maldakal project" turns *"how many vacancies in my project?"* from a correct refusal into a cited answer on line 17. Note the refusal without the note is right, not a bug — the note supplies the missing **referent**, never the answer.
- **Cache the digitised output of both demo docs to disk.** This is the offline fallback for a dead API during the demo, and it makes iteration fast (digitisation is the slow, paid step — don't re-run it on every code change).
- The final artifact is an **answer record** (shareable, verifiable), not a chat log.

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

- Models: **`sarvam-30b`** (default choice here) or `sarvam-105b`. `sarvam-m` is **deprecated** and now errors.
- `temperature=0.0` + fixed `seed`. Note `seed` is best-effort, **not guaranteed** — do not stake demo repeatability on it; stake it on the cached digitised text.
- `response_format` = `{"type": "json_schema", "json_schema": {"name": ..., "schema": ..., "strict": true}}` to force `{answer, supporting_quote, found}`.
- **Set `reasoning_effort=None` and keep `max_tokens` generous.** Reasoning is on by default (`sarvam-105b` defaults to `"low"`), and reasoning tokens can consume the whole budget, returning empty structured output. This is the most likely silent failure in the QA step.
- **Do not pass `wiki_grounding`** — no longer supported on `sarvam-30b`/`sarvam-105b`. Groundedness comes from the prompt plus the string-match gate, not from this flag.

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
.venv/bin/python -m pytest                          # 53 tests
.venv/bin/python -m pytest --cov=askdoc --cov-report=term-missing

.venv/bin/python -m askdoc.cli digitise --doc doc_a # cached; --force re-runs the PAID call
.venv/bin/python -m askdoc.cli show     --doc doc_a # print cached digitised text
.venv/bin/python -m askdoc.cli ask      --doc doc_a "question" ["question2" ...]

# --- frontend (Next.js 16, TS, Tailwind) ---
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
