# Submission — Ask the Document

## Title

**Ask the Document** — a trustworthy reader for one dense official page.

## The 30-second context

> India runs on dense official pages: a government circular, an insurance clause, an exam notice, a land record. They are written in Tamil or Telugu, they matter enormously to the person holding them, and they are almost unreadable.
>
> The obvious fix — point an LLM at it — fails in the one way that matters. A confident wrong answer about your own eligibility is worse than no answer, because you act on it.
>
> Ask the Document answers a plain-language question **with the exact line of the page it came from — or it says the page doesn't say.** There is no third state and no "I think". The model is never allowed to write the quote: it points at line numbers, and we slice the citation out of our own digitised copy. Paraphrase is not detected, it is structurally impossible.

## What is actually being claimed

| Claim | Basis |
|---|---|
| The citation is verbatim | Sliced from our NFC-normalised copy at a verified line range. The model emits **numbers**, never quote text |
| A refusal is honest about *why* | Four distinct `RefusalReason`s. "The page doesn't say" and "that's more than I can quote" are never the same message |
| It works on a second document with no code changes | doc_a Tamil, doc_b Telugu, same pipeline |
| Measured, not asserted | 12 labelled cases × 3 runs, scored for **correct / irrelevant / false refusal** |

**Known limitation, stated up front:** verification guarantees the citation is *real*, not that it is *relevant*. The model can point at genuine verbatim text that answers a different question. Measured at ~3%. No string or line check can catch that — it is a retrieval problem on a separate axis.

## Sarvam APIs used

| API | Where |
|---|---|
| **Document Digitization** | The scored capability. Async job; we read the **page JSON blocks**, not `document.md` |
| **Chat Completions** (`sarvam-105b`) | Grounded QA with JSON-schema structured output, plus intent classification |
| **Saaras v3** (speech-to-text) | Ask a question out loud |
| **Bulbul v3** (text-to-speech) | Hear the answer, or hear the cited line as written |
| **Text LID** | Language detection for uploaded pages |

## Links

- Repo: _(fill in)_
- Demo video fallback: _(fill in — see below)_
- Public URL: **not deployed.** Per §4's stated fallback, the demo runs locally over screen-share

---

# Demo script — 3:00

Run it from a **fresh browser reload**. That is a complete reset: the backend stores nothing between requests and the conversation is deliberately not persisted, so no run can inherit anything from the run before it.

| Time | Beat | What to say |
|---|---|---|
| **0:00–0:25** | Open `doc/doc_a` — the Tamil exam notice, 65 numbered lines | "This is a real TNPSC page. If you need one fact out of it, you cannot skim it — and you cannot afford to guess." |
| **0:25–1:05** | Tap the mic, **ask in Tamil out loud**: *"விடைத்தாளை நிரப்ப எந்த வகையான பேனாவைப் பயன்படுத்த வேண்டும்?"* Let the transcript land in the box, **then** press Ask | "It writes down what it heard and stops. I check it before it's asked — because a misheard question comes back as a perfectly verified answer to something I never said." Answer appears; **line 40 highlights on the page.** |
| **1:05–1:35** | Ask the starter marked *not on this page* | "It doesn't say. That's the feature. It would rather refuse than guess — and it tells me *why* it refused: the page is silent, not that I hit some limit of its own." |
| **1:35–2:10** | Switch to **doc_b — Telugu.** Ask the vacancies question → correct refusal. Add the note *"I'm applying to the Maldakal project."* Ask again → **cited answer, line 17** | "Second document, second language, no code changes. And the note didn't supply the answer — the page always had it. It supplied the missing *referent*: which project is mine." |
| **2:10–2:40** | Press **"The page"** on the citation | "That's Bulbul reading the line — and it's the *page's* words, not the model's. Two separate buttons, because heard rather than seen you can't tell them apart, and that difference is the whole product." |
| **2:40–3:00** | Close on the invariant | "The model never types the quote. It points at line numbers, we verify the range, and we slice the citation out of our own digitised copy. Paraphrase isn't caught — it's impossible." |

## If the API dies mid-demo

1. **Both demo pages are cached to disk and render with no network at all** — the document, its line numbers and its starter questions are all local. Verified with `SARVAM_API_KEY` unset.
2. Only `/ask`, `/speak` and `/transcribe` need the API. If chat is down, the page still renders and you narrate from the recorded video.
3. `429` and `502` surface as **errors, never as "not stated"** — a dead service must never be reported as the document being silent.

## Pre-flight checklist

- [ ] `SARVAM_API_KEY` exported in the backend shell
- [ ] Backend on `:8000` (`/health` returns 200), frontend on `:3000`
- [ ] **Hard reload** the browser — fresh state
- [ ] Mic permission already granted (do this before you start, not on camera)
- [ ] Sound on and audible on the shared screen
- [ ] Decide whether the extra uploaded Telugu doc stays in the list or goes
