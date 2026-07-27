# Source Documents — "Ask-the-Document" demo inputs

Two dense, real, regional-script bureaucratic pages for Doc A + Doc B (the "hard, unseen-by-judges input"). Both are the kind of document a citizen has real, answerable questions about (dates, fees, age limits, vacancies) — ideal for the cite-or-silence demo.

> Handling note: download each file on your own device (no restriction there), then either (a) attach it in this chat so I can read it and write exact expected answers, or (b) drop it in your build folder for the M1 Digitise test. Keep a **cached copy of each digitised output** on disk as the offline demo fallback (per IDEA_SCOPE §5).

---

## Doc A — Tamil (recommended, high confidence Tamil-script) ✅

> ⚠️ **SUPERSEDED — read this before using anything below.** The URL serves the TNPSC **question-paper booklet**, not a recruitment notification: it contains no vacancies, no fees and no dates, so questions 1–3 below have no answer on the page and were never usable.
>
> What actually shipped is that booklet's **cover page** (`docs/doc_a_page.png`) — 13 nested Tamil instructions, mixed script, a bordered grid — digitised to 65 numbered lines. Page 96 of the same PDF is an English translation of that cover, which made it a free ground-truth oracle.
>
> **The live demo questions are `frontend/lib/questions.ts`; the labelled ground truth is `backend/askdoc/evalset.py`.** Both are maintained. Treat this file as the sourcing record for where the documents came from, not as the question set.

**TNPSC Group IV — General recruitment notification (Tamil version)**
- Link: https://tnpsc.gov.in/Tentative/Document/01_2024_GR_IV_GENERAL_TAMIL.pdf
- Also browse the Tamil notifications list: https://www.tnpsc.gov.in/Tamil/Notification.aspx
- Why it's a strong input: dense Tamil script, multi-column tables (posts, vacancies, pay scale), age limits, application-fee amounts, key dates, and eligibility clauses — a rich surface of factual questions, plus at least one thing that is *not* stated (for the honest-refusal beat).

### Demo questions (product extracts the answers; fill expected values after first Digitise)
1. காலி பணியிடங்கள் மொத்தம் எத்தனை? *(How many total vacancies?)* → `[fill after digitise]`
2. விண்ணப்பக் கட்டணம் எவ்வளவு? *(What is the application fee?)* → `[fill]`
3. விண்ணப்பிக்க கடைசி தேதி என்ன? *(Last date to apply?)* → `[fill]`
4. **Out-of-scope (must refuse):** தேர்வு மையம் சென்னையில் எந்த முகவரி? *(Exact exam-centre address in Chennai?)* → expected: **"இந்த ஆவணத்தில் குறிப்பிடப்படவில்லை" / "not stated in this document."**

---

## Doc B — Telugu (pick one Telugu-script page; verify script when you open it)
Government recruitment/scheme PDFs are often English even on state sites, so **eyeball that it's Telugu script** before locking. Good avenues, in order of preference:
1. **TSPSC / APPSC notification, Telugu (తెలుగు) version** — check the commission sites for a తెలుగు copy of a current notification:
   - TSPSC: https://websitenew.tspsc.gov.in  ·  APPSC: https://psc.ap.gov.in
2. **Telangana/AP welfare-scheme application form or guidelines in Telugu** (pension / ration / Rythu / Praja Palana) — dense, form-like, excellent for Sarvam Vision (tables + fields).
3. **Fallback robustness input:** a Telugu newspaper front page (Eenadu/Sakshi e-paper) — not bureaucratic, but a genuinely hard multi-column Telugu-script scan to prove the reader isn't hand-tuned.

### Demo questions (Telugu; adapt to the doc you pick, then fill answers)
1. ఈ దరఖాస్తుకు చివరి తేదీ ఏమిటి? *(What is the last date?)* → `[fill]`
2. ఫీజు / ఆదాయ పరిమితి ఎంత? *(Fee / income limit?)* → `[fill]`
3. వయస్సు పరిమితి ఎంత? *(Age limit?)* → `[fill]`
4. **Out-of-scope (must refuse):** [ask something plausibly related but absent from the page] → expected: **"ఈ పత్రంలో పేర్కొనలేదు" / "not stated in this document."**

---

## Why this pairing works for the rubric
- **Job-to-be-done:** two different real docs → proves repeatability, not hand-tuning (path to L5).
- **Document Intelligence (scored):** dense Tamil + Telugu script with tables = the hard case the ladder rewards.
- **Creativity / Delight:** each doc carries a deliberate out-of-scope question → the honest refusal beat.
- **Language coverage:** one Tamil + one Telugu — both languages you can verify natively.

## Open item
Exact figures aren't filled here because the source sites blocked automated reading. Attach the two PDFs in chat (or paste their digitised text) and I'll fill every expected answer and wire them into the M1 test.
