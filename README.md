# Ask the Document

A trustworthy reader for one dense official page.

It answers a plain-language question about a Tamil or Telugu government circular, insurance clause, exam notice or land record **with the exact line of the page the answer came from — or it says the page doesn't say.** There is no third state and no "I think".

Built solo for the Sarvam Epoch Buildathon (26 Jul), in a six-hour sprint.

---

## The problem

India runs on dense official pages. They are written in Tamil or Telugu, they matter enormously to the person holding them, and they are close to unreadable.

The obvious fix — point an LLM at the page — fails in the one way that matters. A confident wrong answer about your own eligibility is worse than no answer, because you act on it.

## The core invariant

**The citation shown to the reader is always sliced out of our own copy of the digitised text. Text written by the model never becomes a citation.**

```
1. Digitise the page (Sarvam Vision) → text, NFC-normalised once, cached
2. Render it with line numbers
3. Ask sarvam-105b for {answer, found, quote_from_line, quote_to_line}
   ↑ the model points at line numbers. It never retypes the quote.
4. Verify the range deterministically: in bounds, not inverted, not blank
5. Slice those lines out of our text — that is the citation
6. Range invalid → "not stated in this document"
```

`found` is trusted in **one direction only**: a "no" is honoured immediately, because refusing is the safe direction. A "yes" earns nothing until the range is verified.

The first version had the model retype the quote and string-matched it. Measured on the real Tamil page, that falsely refused **~1 in 3 answerable questions** — the model paraphrased at the margins despite an explicit prompt rule naming the exact words not to substitute. Prompt pressure did not close it.

Line anchoring makes paraphrase **structurally impossible** rather than detected-after-the-fact.

## What is actually being claimed

| Claim | Basis |
|---|---|
| The citation is verbatim | Sliced from our NFC-normalised copy at a verified line range. The model emits **numbers**, never quote text |
| A refusal is honest about *why* | "The page doesn't say" and "we couldn't verify a citation" are distinct `RefusalReason`s and never share a message. Reporting our own limit as the document's silence would tell the reader the page lacks something it contains |
| It refuses only when the page genuinely doesn't answer | Three checks that refused for *other* reasons — paraphrase mismatch, an LLM relevance judge, and excessive citation width — were each measured and deleted. All three destroyed more correct answers than they saved |
| It works on a second document with no code changes | `doc_a` Tamil, `doc_b` Telugu, same pipeline |
| Measured, not asserted | 12 labelled cases (7 Tamil, 5 Telugu; 8 answerable, 4 must-refuse) × 3 runs, scored separately for **correct / irrelevant / false refusal** |

**Known limitation, stated up front:** verification guarantees the citation is *real*, not that it is *relevant*. The model can point at genuine verbatim text that answers a different question. Measured at ~3%. No string or line check can catch that — it is a retrieval problem on a separate axis.

## Features

- **Ask about any page you upload.** PDF, PNG or JPEG. The language is detected rather than configured.
- **Two demo documents built in**, cached to disk so they render with no network at all.
- **Voice in and out.** Ask out loud (Saaras v3); hear the answer, or hear the cited line as the page wrote it (Bulbul v3). Two separate buttons, because heard rather than seen you cannot tell the model's words from the page's — and that difference is the whole product.
- **Multi-turn follow-ups and reader notes.** A note can change *which* lines get cited; it can never become a citation.
- **Shareable answer records.** A link re-checks the citation against the document when it opens.

### Language detection

Sarvam's digitiser has no auto-detect — `language` is mandatory — so detection needs text, text needs digitisation, and digitisation needs the language. Broken with a probe pass:

```
validate → sha256 → doc_id        ← same bytes = cache hit, no paid call
        → digitise with a probe language
        → sample the longest block → /text-lid
        → verify LID against our own Unicode-block count
        → re-digitise in the resolved language (skipped if it matches the probe)
```

**LID proposes; our own script count disposes.** Text LID knows 11 languages, digitisation accepts 23, and LID answers with one of its 11 rather than admitting ignorance. So character evidence outranks it (`ৰ`/`ৱ` mean Assamese, not Bengali), and an ambiguous script is accepted only when LID names a language actually written in it. When we cannot tell, we ask the reader rather than guess.

## Sarvam APIs used

| API | Where |
|---|---|
| **Document Digitization** | The scored capability. Async job; we read the **page JSON blocks**, not `document.md` |
| **Chat Completions** (`sarvam-105b`) | Grounded QA with JSON-schema structured output, plus intent classification |
| **Saaras v3** | Speech to text — ask a question out loud |
| **Bulbul v3** | Text to speech — hear the answer or the cited line |
| **Text LID** | Language detection for uploaded pages |

## Quickstart

```bash
export SARVAM_API_KEY="..."          # dashboard.sarvam.ai — shown once at creation

# backend (Python 3.12)
cd backend
uv venv --python 3.12 && uv pip install -U sarvamai fastapi "uvicorn[standard]" \
    pytest pytest-cov python-multipart pypdf
.venv/bin/python -m uvicorn askdoc.api:app --port 8000 --host 127.0.0.1 --reload

# frontend (Next.js 16, TypeScript, Tailwind)
cd frontend && npm install && npm run dev
```

⚠️ **Always pass `--reload`.** Without it uvicorn serves the module it imported at boot, so new routes never appear — a POST to an existing path returns `405 Method Not Allowed` while the tests stay green, because `TestClient` imports fresh from disk and never sees the stale process.

The two demo documents are already digitised and committed, so the app works offline. Re-running digitisation costs a paid API call:

```bash
.venv/bin/python -m askdoc.cli digitise --doc doc_a   # cached; --force re-runs the PAID call
.venv/bin/python -m askdoc.cli show     --doc doc_a
.venv/bin/python -m askdoc.cli ask      --doc doc_a "question"
```

## Tests and measurement

```bash
cd backend
.venv/bin/python -m pytest                                  # 384 tests
.venv/bin/python -m pytest --cov=askdoc --cov-report=term-missing
.venv/bin/python -m askdoc.evaluate --runs 3                # the labelled set
```

`evaluate` scores three distinct outcomes — **correct**, **irrelevant** (cited real text answering something else), and **false refusal** — because they have different causes and different fixes. Do not tune the prompt or the gate without running it before and after.

## Layout

```
backend/askdoc/
  digitise.py  cache.py  tables.py     ingestion: Sarvam Vision → normalised text
  upload.py    detect.py  jobs.py      uploads: validate → probe → detect → re-read
  prompts.py   qa.py      structured.py grounded QA with structured output
  lines.py     gate.py                 line anchoring and deterministic verification
  pipeline.py  intent.py  records.py   orchestration, question-vs-note, shareable records
  voice.py     starters.py             speech in/out, generated opening questions
  api.py       cli.py                  HTTP surface and console slice
  evalset.py   evaluate.py             12 labelled cases, scored three ways

frontend/app/
  /                library and upload
  /doc/[docId]     the reader — one document, always
  /r/[recordId]    a shared answer record
```

## Non-goals

No multi-document RAG or corpus — the library is a switcher, one document per conversation. No legal or financial advice; it reports what the page says. No accounts. No translation of the document into a third language.

## Documentation

- [`CLAUDE.md`](CLAUDE.md) — architecture, invariants, and the reasoning behind decisions that were measured and reversed
- [`IDEA_SCOPE_1.md`](IDEA_SCOPE_1.md) — scope, milestones, non-goals, parking lot
- [`SUBMISSION.md`](SUBMISSION.md) — submission assets and the timed demo script
