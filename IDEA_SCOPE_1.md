# IDEA_SCOPE.md — "Ask-the-Document" (Trustworthy Tamil/Telugu Document Reader)

> Control plane for the build. Read this before proposing or making any change.
> Sarvam Epoch Buildathon · Razorpay Arena · Sun 26 Jul · Build sprint 10:30 AM–4:30 PM IST · Submit 4:30 PM · Demos 5:30–6:30 PM IST.
> Builder: solo. Edge: raw build speed + native Tamil/Telugu verification. Demo format: 3 min (30s context / 30s friction / 2 min live) with a **recorded fallback**.

---

## 0. One-line product

A trustworthy reader for a dense official document that answers plain-language questions **with a verbatim source quote — or honestly says the document doesn't say so** — so a person can act on bureaucratic paperwork without being misled.

> **Scope widened post-freeze (26 Jul).** Written as Tamil/Telugu-only; uploads now accept all 23 languages Sarvam digitises, with the language detected rather than configured (§7). **The evaluation set did not widen with it** — it is still Tamil and Telugu, so those two remain the languages in which anything is *claimed*. Everywhere below that says "Tamil/Telugu" and describes a **measurement, a demo document or an acceptance test** is still exactly right and should not be broadened.

- **User:** someone holding one dense official page (govt circular, insurance clause, exam notice, land record) in a language they speak but cannot parse in officialese, who cannot risk a made-up answer.
- **Job completed:** correct, source-backed answers to real questions about *this* document, plus a clear "not stated here" when it doesn't apply.
- **Hard input:** one dense, real regional-script page — mixed script, legalese, tables, real capture. Both demo documents (Tamil, Telugu) are of this kind.
- **Final artifact / state change:** an **answer record** — each question with its exact source quote highlighted on the digitised page; shareable and verifiable, not just a chat log.

## Scored capability (choose ONE — judges score depth here)

**Sarvam parameter = Document Intelligence** (Sarvam Vision / Digitise).
Additional capability used but **NOT** scored and kept strictly source-constrained: **Chat Completions (Sarvam-30B)** as a grounded QA layer. Anything else is parked (§7).

## 0.1 Provenance & differentiation (finalized)

- **Origin:** derived from the builder's asymmetric fit (solo, fast, native Tamil/Telugu, controllable pipeline) — **not** copied from a named Idea Library entry. (The handbook's concrete Idea Library is embedded in a hidden data block that can't be read without raw HTML / an interactive browser; closest visible handbook lens = "living documents & public records" blended with "institutional workflows.")
- **Honest novelty read:** the *pattern* (document Q&A) is one of the most common hackathon/cookbook builds → low surface novelty. The *edge* is the **deterministic cite-or-silence gate + dense Tamil/Telugu bureaucracy + refusal-as-delight + 2-doc repeatability**. Non-obvious execution, not a new invention — and it only reads as different if the demo makes it visible.
- **Two moves that make the difference legible (do both):**
  1. **Side-by-side contrast** (demo-only, no extra build): run a plain LLM on the same Tamil/Telugu page — it confidently hallucinates; ours refuses and cites. This is the single strongest way to *show* Creativity instead of asserting it.
  2. **Helpful refusal** (small prompt change, add ONLY once the core passes): instead of a bare "not stated," say "not stated here — this page covers X." Turns a refusal into guidance.
- **Rubric hygiene:** Tamil/Telugu counts toward the **Sarvam parameter + asymmetric fit**, NOT Creativity (the rubric excludes language swaps from Creativity). Keep those claims in separate buckets.

---

## 1. Verified Sarvam facts this build depends on

| Thing | Verified detail | Source of truth to re-check at kickoff |
|---|---|---|
| Digitise (Sarvam Vision) | Full-page digitisation → **Markdown / HTML / JSON** (structured page-level JSON returned by default); preserves layout + reading order; tables → MD/HTML; **handwriting supported**. | docs.sarvam.ai/docai + models/sarvam-vision |
| Languages | 23 (22 Indian + English), **incl. Tamil & Telugu**. | same |
| Input limits | PDF / JPEG / PNG (also ZIP of ≤10 flat images); **≤200 MB**, **≤10 pages/job**. Use **one dense page** — comfortably inside. | same |
| Bounding boxes | **NOT documented in the API response.** Color-coded boxes exist only in Sarvam's own editor UI. → **Do NOT depend on coordinates.** Citation = highlighted **verbatim text span** in the rendered digitised page. | same |
| Grounded QA | **Sarvam-30B** Chat Completions; constrain to provided digitised text only via prompt + the faithfulness gate. (`sarvam-m` is **deprecated** and now errors.) | docs.sarvam.ai chat completion |

> **Assumption flagged (verify in M0, do not let it become load-bearing silently):** Digitise quality is good enough on *your specific* Tamil/Telugu page. If not, swap to a cleaner-but-still-dense page. This is the single hardest dependency and M1 exists to kill it early.

### 1a. Verified API integration (exact — hand this to the coding assistant)

> **Re-verified against docs.sarvam.ai (26 Jul).** This section was rewritten after checking the live docs; the pre-sprint draft had drifted. Deltas are listed at the end of this section.

**Auth & setup:** Base URL `https://api.sarvam.ai`. Header `api-subscription-key: <key>` (Bearer also accepted). Get the key at **dashboard.sarvam.ai** — it is shown **once** at creation, save it immediately. Read it from `SARVAM_API_KEY` env, never hardcode. Python SDK: `pip install -U sarvamai` → `SarvamAI(api_subscription_key=...)`. Auth failures return **403** (not 401) with `error.code: invalid_api_key_error`; **429** = rate limit / quota exceeded.
*Unverified — confirm at the dashboard at kickoff:* ₹100 free credits, ₹0.5/page digitise, ~60 req/min.

**Document Digitise = ASYNC JOB — but the SDK collapses it to 5 calls (this is EASIER than the earlier draft assumed):**

```python
from sarvamai import SarvamAI
client = SarvamAI(api_subscription_key=os.environ["SARVAM_API_KEY"])

job = client.document_intelligence.create_job(language="ta-IN", output_format="md")  # 1. initialise
job.upload_file("doc_a.pdf")                                                          # 2. upload
job.start()                                                                           # 3. start
status = job.wait_until_complete(timeout=300)                                         # 4. poll
job.download_output("output.zip")                                                     # 5. download
```

- `language` (**not** `language_code`): `ta-IN` Tamil, `te-IN` Telugu. *Default is `hi-IN` — you MUST set it.*
- `output_format`: `"md"` | `"html"` | `"json"`. `"markdown"` returns 400 — use `"md"`. **JSON page-level data is always in the ZIP regardless of format**; `"json"` returns *only* the JSON and drops the md/html. → **Use `"md"`**: you get renderable Markdown for the M2 highlight UI *and* the structured JSON.
- Python SDK `wait_until_complete()` waits **forever** without an explicit `timeout` — always pass one.
- Job states: `Accepted` → `Pending` → `Running` → `Completed` | `PartiallyCompleted` | `Failed`. **Handle `PartiallyCompleted` — it is not success.**
- Limits: PDF ≤10 pages / PNG / JPEG / ZIP (≤10 flat images), **≤200 MB**. **No coordinate/bbox in the API** — citation = verbatim text span (confirmed).
- Raw REST equivalent exists (`POST /doc-digitization/job/v1`, `.../{job_id}/status`, etc.) if you need it, but prefer the SDK — it removes the presigned-link dance entirely.

**Grounded QA (Chat):** `POST /v1/chat/completions`, `model: "sarvam-30b"` (`sarvam-105b` if you need more reasoning). `sarvam-m` is **deprecated and now errors**. Use:
- `temperature: 0` + a fixed `seed`. ⚠️ `seed` is **best-effort, not guaranteed** — do not stake demo repeatability on it; stake it on the **cached digitised text** (§5).
- `reasoning_effort=None` (Python) / `null` (REST), and keep **`max_tokens` generous**. ⚠️ Reasoning is ON by default (`sarvam-105b` defaults to `"low"`) and reasoning tokens can consume the entire budget, returning **empty structured output**. This is the most likely silent failure in the QA step — it will look like "the JSON parse randomly fails."
- **Do NOT pass `wiki_grounding`** — no longer supported on `sarvam-30b`/`sarvam-105b`. Staying inside the document comes from the prompt **plus the faithfulness gate**, not from a flag.
- `response_format` = `{"type": "json_schema", "json_schema": {"name": ..., "schema": ..., "strict": true}}` forcing `{ "answer": string, "supporting_quote": string, "found": boolean }`. Then **string-match `supporting_quote` against the digitised text**; if not found → override to "not stated in this document." *That check is the faithfulness gate — the model's own `found` flag is not trusted alone.*

**Deltas from the pre-sprint draft** (if you memorised the old version, re-read): `wiki_grounding: false` → **remove it, unsupported**; 6-step REST dance → **5 SDK calls**; ≤50 MB → **≤200 MB**; ≤10 pages/*project* → per **job**; `output_format: "json"` → **`"md"`**; "`seed` = repeatable demos" → **best-effort only**; plus the new `reasoning_effort` / `max_tokens` trap above.

---

## 2. Creativity & Delight thesis (must stay structural, not cosmetic)

- **Creativity — "Cite-or-stay-silent":** every answer is gated on a verbatim quote that is **deterministically string-matched against the digitised text**. If the model's quote is not literally present in the source, the answer is downgraded to *"not stated in this document."* The refusal is only *possible* because of this mechanism — that is the non-obvious workflow choice.
- **Delight — honest judgment:** the moment it **declines** to answer an out-of-scope question (and is right). Confidence through honesty, at the user's real point of friction (fear of being misled).

---

## 3. Milestones (derived from the actual sprint; each has tasks, an acceptance test, and a cut-to fallback)

> Times assume a full 10:30–4:30 sprint. **If you started late, keep the milestone ORDER and jump to each milestone's fallback to compress.** Freeze features at **4:00 PM** no matter what.

### M0 · Setup — 10:30–10:45 (15 min)
- **Tasks:** create a key at dashboard.sarvam.ai (confirm credits); `export SARVAM_API_KEY=...`; `pip install -U sarvamai`; confirm a Chat call returns text (`model: sarvam-30b`); **run the full 5-call Digitise job once** (`create_job` `ta-IN`/`te-IN` → `upload_file` → `start` → `wait_until_complete` → `download_output`) on any small file; scaffold repo (FastAPI or one Next.js route — whatever you're fastest in); load your 2 candidate demo pages.
- **Acceptance:** the Digitise ZIP downloads and contains real text for a test file; one Chat call returns text **with a non-empty structured payload** (see the `reasoning_effort` trap in §1a). Key + credits confirmed working.
- **If behind → cut to:** get just the Digitise job round-trip working; defer chat wiring to M1.
- **Note:** the SDK removes the presigned-link dance this milestone was sized around — if it goes fast, bank the time for M1, don't spend it on polish.

### M1 · Ugly end-to-end vertical slice (de-risk the hardest dependency) — 10:45–11:45 (Hour 1)
- **Tasks:** hardcode ONE Tamil/Telugu page → run the Digitise job (language `ta-IN`/`te-IN`, `output_format: "md"`) → read the text out of the ZIP → **cache it to disk immediately** (never re-digitise on every iteration — it is the slow, paid step) → hardcode ONE question → call `sarvam-30b` with `temperature 0`, `reasoning_effort=None`, generous `max_tokens`, `response_format` forcing `{answer, supporting_quote, found}`, prompt = "answer ONLY from this text; quote the exact supporting sentence" → **string-match the quote against the digitised text** → print answer + verified quote (or "not stated") to console. No UI. No error handling.
- **Acceptance test (the Hour-1 gate):** on your **real demo page**, you get one **correct** answer whose quote **actually appears** in the digitised text (you verify natively). If Digitise mangles the page, switch to backup page NOW.
- **Rubric it moves:** Job-to-be-done L1→L3 (one real usable result); Document Intelligence baseline proven on ugly input.
- **If behind → cut to:** prove it in a plain script; this slice is the minimum that must exist.

### M2 · Faithfulness gate + refusal + minimal UI — 11:45–1:15 (90 min)
- **Tasks:** implement the **verbatim string-match check** (normalise whitespace/case; the returned quote must be a substring of the digitised text, else return *"not stated in this document"*). Build a minimal web view: preselect the page (upload optional), type a question, show the answer + the **highlighted quote** on the rendered digitised text + a clear "not stated" state.
- **Acceptance test:** on the demo doc, **3 real questions** answered with correct highlighted quotes **and 1 out-of-scope question correctly refused**.
- **Rubric it moves:** Creativity (structural cite-or-silence), Delight (honest refusal), Job-to-be-done → L4.
- **If behind → cut to:** keep console output + a **static** highlighted render of one answer; drop live upload, use the preloaded doc.

### M3 · Repeatability + second doc + memory — 1:15–2:30 (75 min)
- **Tasks:** run the exact flow on a **2nd** Tamil/Telugu doc with **no code changes** (proves it isn't hand-tuned). Persist the session's Q&A history and **one user correction** ("treat term X as Y / this clause refers to Z") and carry it into later answers.
- **Acceptance test:** doc #2 answers 3 questions correctly + refuses 1; a correction persists and visibly changes a later answer.
- **Rubric it moves:** Job-to-be-done → L5 path (repeated cases), Memory & Context L2→L4 (governed continuity + corrections).
- **If behind → cut to:** keep the 2-doc repeatability, **drop the correction/memory feature to the parking lot.**

### M4 · Trust UX / Delight polish + public link — 2:30–3:30 (60 min)
- **Tasks:** clean the **answer record** view (question · answer · highlighted quote · confidence/"not stated" state); make the refusal visually unmistakable; add **export/share** of the answer record; deploy to a **public URL**.
- **Acceptance test:** a non-builder can read the answer record and find the source; the public link loads on a phone.
- **Rubric it moves:** Delight, Impact legibility (a shareable proof artifact).
- **If behind → cut to:** local screen-share instead of public link; export a simple HTML/PDF record.

### M5 · Demo hardening (PROTECTED — do not skip) — 3:30–4:30 (60 min)
- **Tasks:** run all cases **3× each**; add state reset between runs; prepare fallback inputs (pre-digitised JSON cached so a dead API can't kill the demo); **record the 2-min demo video fallback**; verify public link; assemble submission assets (title, 30s context, links); **two timed rehearsals** of the full 3-min demo.
- **Acceptance test:** two clean rehearsals **under 3:00**; recorded fallback exists; submission fields ready **before 4:30**.
- **Stop condition:** at **4:00 PM freeze features** — bug-fix and rehearse only. Submit by **4:30**.

---

## 4. Test inputs (prepare in M0/M1)

- **Doc A (primary)** and **Doc B (backup)**: two real dense Tamil/Telugu pages (mixed script + a table if possible), ≤200 MB, single page each.
- For each: **3 in-scope questions** with the expected source quote noted, **1 deliberately out-of-scope question** (must be refused).
- Keep the digitised JSON/Markdown for both cached on disk as the offline fallback.

## 5. Failure handling (in product)

- Digitise fails/times out → use the **cached digitised text**.
- Model returns a quote **not** found in source → return *"not stated in this document"* (never guess).
- API down during demo → switch to **pre-digitised cache + recorded video fallback**.
- Ambiguous/low-confidence answer → surface uncertainty rather than assert.

## 6. Non-goals (do not build; protect the core)

No live voice/telephony · no multi-document RAG/corpus · no legal or financial *advice* (it reports what the document says, with a "not a lawyer/advisor" caveat) · no visual bounding-box pins in v1 · no third-language translation in v1 · no auth/accounts.

## 7. Parking lot (only if core is done + rehearsed; never onto the critical path without an explicit rescope)

Translate answer to a third language (Mayura/Sarvam-Translate) · mobile-native polish.

*Removed from this list because they shipped:* TTS/STT voice · additional languages beyond Tamil/Telugu · multi-page docs (uploads accept up to 10 pages — the API's per-job limit; over-limit is rejected, never truncated).

**Shipped 14:55 (explicit rescope):** TTS read-aloud (Bulbul v3) and STT question input (Saaras v3). STT was not on this list; it is adjacent to the §6 "no live voice/telephony" non-goal, which is read here as ruling out a voice *agent* or phone line, not a push-to-talk mic on the existing text box. Noted rather than assumed.

**Visual bbox pins — rescoped, not deferred.** This was parked as blocked on data; the data is in fact stored (`Block.x1..y2`). The real blocker is **granularity**, measured on the cached docs: doc_a has **5 blocks for 65 lines** (~13 lines each), so a pin would box a fifth of the page — *coarser than the line highlight we already render*. Shipping it would make the signature feature visibly worse on the primary demo doc. Also: `Block` stores no page index, so doc_b's 2 pages are ambiguous, and doc_b is a PDF with no rasterised image. Not a time problem; a design one.

**Additional languages — SHIPPED as an explicit rescope (26 Jul, post-freeze), and the original objection still stands in part.**

Upload any page and the language is detected rather than configured: probe digitisation → Sarvam `/text-lid` → verification against our own Unicode-block count → re-read in the resolved language. All 23 digitisation languages are selectable, and an ambiguous script asks the reader instead of guessing. See CLAUDE.md "Uploaded documents".

The objection above was *"cheap and dishonest — no eval doc, no hand-read ground truth, so we would be demoing a capability we cannot claim works."* Half of it is answered and half is not, and the difference matters:

- **Answered:** detection itself is deterministic where it can be and refuses where it cannot, so it is not a claim resting on vibes.
- **NOT answered:** `evalset.py` still contains only Tamil and Telugu cases. **Accuracy in the other 21 languages is unmeasured.** Do not claim it works in Hindi or Bengali — claim that the pipeline accepts them and that nothing about the citation invariant is language-specific.
- Also unmeasured: `PROBE_LANGUAGE` assumes a wrong language hint still returns correctly-scripted text. Never spiked.

---

## 8. Demo script (3:00 — rehearse twice in M5)

- **0:00–0:30 · Context:** who the user is and the dense-document problem, in plain language.
- **0:30–1:00 · Friction:** today you guess, ask a middleman, or paste it into a generic chatbot that **confidently hallucinates** — costly when it's your land record or insurance clause.
- **1:00–3:00 · Live:**
  1. Upload/open the real Tamil/Telugu page → Digitise.
  2. Ask **Q1, Q2, Q3** → each returns an answer with the **highlighted source quote**.
  3. **Contrast beat (differentiation):** paste the same question into a plain LLM → it confidently invents an answer; ours cites the source. *(makes the creativity visible)*
  4. Ask the **out-of-scope** question → it **refuses honestly** ("not stated here — this page covers X"). *(the Delight beat)*
  5. Apply a **correction** → re-ask → the fix sticks. *(Memory beat)*
  6. Switch to **Doc B** → answer to prove **repeatability, not hand-tuning**.
- **Recorded fallback** ready to play if anything stalls.

## 9. Evidence map (which exact moment proves which parameter — no double-counting)

| Parameter | The one moment that proves it |
|---|---|
| Job-to-be-done | 3 correct **cited** answers across **2 docs**, no builder intervention → L4–L5. |
| Document Intelligence (Sarvam) | Digitise pulling a correct quote from the **dense mixed-script** page (tables/reading order intact). *Accuracy counts here only — not toward Delight.* |
| Creativity | The **refusal** + the **side-by-side contrast** (plain LLM hallucinates, ours cites) — possible only because of the verbatim faithfulness gate (structural, not cosmetic). |
| Delight | The honest "not stated here" + the correction sticking. *The trust experience — not the OCR accuracy.* |
| Memory & Context | The persisted **correction** carried into a later answer within the session. |
| Impact | Context framing: access to otherwise-unreadable bureaucracy; one metric — e.g. % correct-and-cited vs a generic chatbot's hallucination rate, or time-to-trusted-answer. |

---

## 10. Status tracker (update as you build)

> Updated 27 Jul.

| Item | implemented | working locally | passed acceptance | demo-ready |
|---|---|---|---|---|
| M0 setup | ☑ | ☑ | ☑ | — |
| M1 vertical slice | ☑ | ☑ | ☑ | ☑ |
| M2 gate + refusal | ☑ | ☑ | ☑ | ☑ |
| M2 minimal UI | ☑ | ☑ | ☑ | ☑ |
| M3 2nd doc (repeatability) | ☑ | ☑ | ☑ | ☑ |
| M3 multi-turn conversation | ☑ | ☑ | ☑ | ☑ |
| M3 memory / corrections | ☑ | ☑ | ☑ | ☑ |
| M4 trust UX + share link | ☑ | ☑ | ☑ | ☑ |
| M5 hardening + demo script | ☑ | ☑ | ☑ | ☑ |
| *rescope:* voice in/out | ☑ | ☑ | ☑ | ☑ |
| *rescope:* upload + language detection | ☑ | ☑ | ⚠ | ☐ |

⚠ **Upload + language detection is the one row that is not demo-ready, and deliberately so.** It is implemented and unit-tested (`detect` 51 tests, `upload` 46, both at 100% line coverage), but its accuracy outside Tamil and Telugu is unmeasured, and `PROBE_LANGUAGE` rests on an assumption that was never spiked (see §7). It is a capability to *show*, not a capability to *claim*. The scripted demo runs on `doc_a`/`doc_b`.

**Measured quality (`python -m askdoc.evaluate --runs N`):** **~93%** across 12 labelled cases on both documents — 8 answerable, 4 must-refuse. Observed runs: 96%, 96%, 88%, 96%, 92%, 89% — **216 trials; quote the range (88–96%), not the best run.** Every remaining miss is the same *irrelevant citation* failure (real verbatim text answering a different question), concentrated on the Tamil `விடை தெரியவில்லை` question where `தெரிவித்து` is a lexical decoy — it failed 3/3 in the M5 run.

**The M5 run is the one to trust: 32/36, 4 irrelevant, and *zero false refusals*.** That asymmetry is the one that matters on stage. A false refusal is visibly wrong to anyone watching; an irrelevant citation on a question that is not in the demo set is not on the demo path at all. None of the four misses touch a scripted beat. **384 unit tests.**

**Honest-refusal fix (14:00) — this had shipped broken.** "Help me understand the notification" was refused by the fixed 8-line cap and rendered to the reader as *"This page doesn't say"* — about a page that says it plainly. A limit of ours was reported as the document's silence, which is worse than a hallucination: the reader walks away believing the page lacks something it contains. Fixed on both axes — the cap was made proportional (`clamp(ceil(0.25×lines), 8, 30)`), and `RefusalReason` now distinguishes "the page is silent" from "we could not cite it", with different wording in the UI. That question now answers, citing lines 5–19.

**Superseded at 15:10 — the proportional cap was removed entirely.** It shipped the *same* bug the fixed cap did: a wide citation that was correct and fully verified was still thrown away. Width is now measured and labelled (`citation_is_broad`), never refused, and `RefusalReason.CITATION_TOO_BROAD` is gone. See CLAUDE.md "The span cap was removed". Three checks have now been deleted for the same reason — paraphrase matching, the relevance judge, and the width cap — and the pattern is over-trusting our own gates.

**Table citations fixed (13:15).** The digitiser emitted one table cell per line, so a cited line read `<td>09</td>` — verbatim but worthless as evidence. `tables.flatten_tables` now rewrites each row onto one line at ingestion; a cited row reads `| | మొత్తం: | 64 | 09 | 73 |` and proves its own arithmetic. Doc B: 125 → 86 lines, no accuracy regression.

**Acceptance evidence (11:56 IST):**
- **M1:** Doc A (TNPSC Tamil, pure scan) digitised in 11 s → 4478 chars across 5 layout blocks; answers cite verbatim spans whose offsets slice the cached text exactly.
- **M2 gate:** out-of-scope question (`தேர்ச்சி பெற எத்தனை மதிப்பெண்கள்?`) correctly refused — the page is saturated with mark numbers (300, 150, 5) but states no cut-off.
- **M3 repeatability:** Doc B (Telugu Anganwadi notification) — **zero code changes**, 3 correct cited answers + 1 correct refusal on the first run. The refused question (`దరఖాస్తు రుసుము ఎంత?`) is published on third-party job sites, so this also proves no training-knowledge leakage.

**M3 memory — working, with a verified demo beat (13:45).** Three earlier attempts at *glossary* corrections all failed: the model already bridges English↔Tamil terms unaided and even reads through a real OCR error in Doc B (`అంగస్ వాడి` for `అంగన్‌వాడీ`). What works is context the model **cannot infer** — the reader's own situation.

The beat, in one input box, 3/3 deterministic:

> **"నేను మల్దకల్ ప్రాజెక్టుకు దరఖాస్తు చేస్తున్నాను."** (statement) → recognised, acknowledged in Telugu, remembered.
> **"నా ప్రాజెక్టులో ఎన్ని ఖాళీలు ఉన్నాయి?"** → *26*, citing line 17 `| 2 | మల్దకల్ | 22 | 04 | 26 |`.
> Without the note the same question is **correctly refused** — the page cannot know which project is "yours".

Two bugs found and fixed on the way, both invisible without live testing: over-fencing the notes block with negatives made the model discount notes entirely; and replaying a pre-note refusal anchored it into repeating that refusal (3/3, unmovable by prompt instruction — fixed structurally by dropping stale refusals).

**Deviations from plan, resolved:**
1. `SOURCE_DOCS.md` Doc A URL serves the TNPSC **question paper booklet**, not a recruitment notification — no vacancies/fees/dates exist in it. Using its **cover page** (13 nested Tamil instructions, mixed script, bordered grid). Page 96 is an English translation of that page = free ground-truth oracle.
2. Core citation mechanism changed from substring-match to **line-anchored** after measuring a ~33% false-refusal rate. See CLAUDE.md "Why line-anchored".
3. `sarvam-30b` → `sarvam-105b` (30b cannot produce reliable structured output).

---

## NEXT SINGLE ACTION

**Create your key at dashboard.sarvam.ai, `export SARVAM_API_KEY=...`, `pip install -U sarvamai`, and get the 5-call Digitise round-trip working (`create_job` `ta-IN`/`te-IN`, `output_format:"md"` → `upload_file` → `start` → `wait_until_complete(timeout=300)` → `download_output`).** Then run M1: one hardcoded Tamil/Telugu page → Digitise → **cache the text to disk** → one question → `sarvam-30b` grounded answer with the quote string-matched against the digitised text, printed to console. Do not build UI until that prints correctly on your real demo page.

> **Riskiest dependency has moved.** The async job is now a thin SDK wrapper, so the real risk is back where §1's flagged assumption always put it: **whether Digitise reads *your specific* dense Tamil/Telugu page well enough.** M1's acceptance gate is what kills that — if the page is mangled, switch to Doc B immediately rather than tuning prompts.
