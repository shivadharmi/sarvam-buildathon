"""HTTP API for the frontend. One verb per endpoint, no session state.

The contract is deliberately small: upload a page, watch it being read, list
documents, fetch one, ask a question. Anything the UI needs to render a
citation is already on the AnswerRecord.

Two rules run through the whole surface:

* **A failure to reach a service is an error, never a refusal.** "We could not
  check" and "the document does not say" are different claims, and collapsing
  the first into the second is the dishonesty this product exists to prevent.
* **Every `detail` string is product copy.** The frontend shows it to the
  reader verbatim, so nothing here leaks a stack trace or a validation dump.

`doc_id` no longer has to appear in a hardcoded allowlist -- uploads mean it
arrives from a URL path. `cache._path_for` is the boundary now: it whitelists
the shape of an id, so an unsafe one cannot name a file at all and simply is
not found.
"""

from __future__ import annotations

from fastapi import (
    BackgroundTasks,
    FastAPI,
    File,
    HTTPException,
    Request,
    Response,
    UploadFile,
)
from fastapi.middleware.cors import CORSMiddleware
from pydantic import Field

from . import cache, jobs, starters
from .config import SUPPORTED_LANGUAGES
from .jobs import Job, JobState, Stage
from .models import (
    AnswerRecord,
    AskRequest,
    DigitisedDoc,
    Frozen,
    NoteAcknowledgement,
    StarterQuestion,
)
from .pipeline import handle
from .sarvam_http import AuthError, ChatError, RateLimitError
from .upload import UploadRejected, store_upload

app = FastAPI(title="Ask the Document", version="0.2.0")

# The frontend is served separately in dev; lock this down before any real
# deployment beyond the demo.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

NO_SUCH_DOCUMENT = "I don't have that document. Upload the page, or pick one from the list."
NO_SUCH_JOB = "That upload is no longer being tracked. Upload the page again."
ORIGINAL_GONE = (
    "I no longer have the original file for this document, so I can't re-read it. "
    "Upload the page again."
)


class JobCreated(Frozen):
    """The reply to a request that starts work.

    Deliberately sparse. A 202 carries only `job_id`, so a client cannot
    mistake an accepted upload for a finished one; `doc_id` and `state` appear
    only alongside a 200, which is the signal that there was nothing to do and
    polling can be skipped.
    """

    job_id: str
    doc_id: str | None = None
    state: JobState | None = None


class LanguageChoice(Frozen):
    """The reader's answer to the picker. Never trusted -- checked against
    `SUPPORTED_LANGUAGES` before it reaches the digitiser."""

    language: str = Field(min_length=1, max_length=32)


def _require(doc_id: str) -> DigitisedDoc:
    try:
        doc = cache.load(doc_id)
    except ValueError:
        # An id that cannot name a file is not a document we have. The 404 is
        # the whole answer; echoing the string back adds nothing.
        raise HTTPException(status_code=404, detail=NO_SUCH_DOCUMENT) from None

    if doc is None:
        raise HTTPException(status_code=404, detail=NO_SUCH_DOCUMENT)
    return doc


def _declared_bytes(file: UploadFile, request: Request) -> int | None:
    """The size the client claims, so an oversized file is refused unread.

    Advisory in one direction only -- `store_upload` still enforces its own
    ceiling while streaming. `UploadFile.size` is exact; the Content-Length
    header includes the multipart envelope and so overstates by a few hundred
    bytes, which is only ever a rounding error against a 25 MB limit.
    """
    if file.size is not None:
        return file.size
    header = request.headers.get("content-length", "")
    return int(header) if header.isdigit() else None


@app.post(
    "/documents",
    response_model=JobCreated,
    response_model_exclude_none=True,
    status_code=202,
)
def create_document(
    request: Request,
    response: Response,
    background: BackgroundTasks,
    file: UploadFile = File(...),
) -> JobCreated:
    """Accept a page and start reading it.

    Declared `def`, not `async def`: reading the body to disk is blocking, and
    FastAPI runs a sync path operation in a threadpool. Ingestion itself is
    handed to a background task, so the reader gets a job id immediately
    instead of holding a connection open for a minute of digitisation.

    Validation happens before any paid call, and its message is the reader's:
    `UploadRejected.message` is copy, written to say what we can take and what
    to do next.
    """
    try:
        stored = store_upload(
            file.file,
            filename=file.filename or "upload",
            declared_bytes=_declared_bytes(file, request),
        )
    except UploadRejected as exc:
        raise HTTPException(status_code=400, detail=exc.message) from exc

    # Identity is the content hash, so the same page uploaded twice is the same
    # document -- and the second upload is free. This is the whole point of
    # hashing rather than minting an id per request.
    cached = cache.load(stored.doc_id)
    if cached is not None:
        response.status_code = 200
        job = jobs.REGISTRY.create(
            doc_id=cached.doc_id,
            label=cached.label or stored.source_filename,
            state=JobState.READY,
            stage=Stage.READY,
            detected_language=cached.language,
            language_source=cached.language_source,
        )
        return JobCreated(job_id=job.job_id, doc_id=cached.doc_id, state=JobState.READY)

    job = jobs.REGISTRY.create(doc_id=stored.doc_id, label=stored.source_filename)
    background.add_task(jobs.run_ingestion, job.job_id, stored.path)
    return JobCreated(job_id=job.job_id)


@app.get("/jobs/{job_id}", response_model=Job)
def get_job(job_id: str) -> Job:
    """Progress of one ingestion.

    `state` is the authoritative field; `stage` narrates it for the reader.
    `needs_language` is a terminal state the picker answers, not an error --
    `error` stays null and `doc_id` is always present, because a state the
    reader cannot answer would be a dead end.
    """
    job = jobs.REGISTRY.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=NO_SUCH_JOB)
    return job


@app.post(
    "/documents/{doc_id}/language",
    response_model=JobCreated,
    response_model_exclude_none=True,
    status_code=202,
)
def set_language(
    doc_id: str,
    choice: LanguageChoice,
    response: Response,
    background: BackgroundTasks,
) -> JobCreated:
    """Re-read a document in the language the reader named.

    This is why the original bytes were kept: the reader answers a picker, not
    a second upload prompt.
    """
    if choice.language not in SUPPORTED_LANGUAGES:
        raise HTTPException(
            status_code=400,
            detail=f"I can't read {choice.language}. Pick one of the languages offered.",
        )

    try:
        cached = cache.load(doc_id)
    except ValueError:
        raise HTTPException(status_code=404, detail=NO_SUCH_DOCUMENT) from None

    prior = jobs.REGISTRY.latest_for(doc_id)
    label = (prior.label if prior else "") or (cached.label if cached else "")

    if cached is not None and cached.language == choice.language:
        # Already what we read it as. Confirming a language must not cost a
        # paid call.
        response.status_code = 200
        job = jobs.REGISTRY.create(
            doc_id=doc_id,
            label=label,
            state=JobState.READY,
            stage=Stage.READY,
            detected_language=cached.language,
            language_source=cached.language_source,
        )
        return JobCreated(job_id=job.job_id, doc_id=doc_id, state=JobState.READY)

    source = jobs.stored_source(doc_id)
    if source is None:
        raise HTTPException(status_code=404, detail=ORIGINAL_GONE)

    job = jobs.REGISTRY.create(
        doc_id=doc_id,
        label=label,
        stage=Stage.DIGITISING_FINAL,
        # Carried forward so the probe pass this document already paid for is
        # not thrown away when the reader picks the language it was read in.
        probe=prior.probe if prior else None,
    )
    background.add_task(jobs.run_language_override, job.job_id, source, choice.language)
    return JobCreated(job_id=job.job_id)


@app.get("/documents", response_model=list[DigitisedDoc])
def list_documents() -> list[DigitisedDoc]:
    """Every digitised document, newest first -- builtin and uploaded alike.

    The full document including `text`, because the UI renders the page from
    this list rather than fetching it again.

    A cache file we cannot parse is deliberately allowed to raise rather than
    being skipped. A document that disappears from the library without a word
    is its own kind of dishonesty -- the reader concludes it was never
    uploaded, and the two demo documents are the offline fallback, so losing
    one silently is the failure most worth making loud. It would also put this
    endpoint at odds with `GET /documents/{doc_id}`, which surfaces the same
    corruption as an error.
    """
    # doc_id breaks ties: timestamps are second-resolution, and two documents
    # cached in the same second must still come back in a stable order.
    return sorted(cache.list_cached(), key=lambda d: (d.digitised_at, d.doc_id), reverse=True)


@app.get("/documents/{doc_id}", response_model=DigitisedDoc)
def get_document(doc_id: str) -> DigitisedDoc:
    return _require(doc_id)


@app.get("/documents/{doc_id}/starters", response_model=list[StarterQuestion])
def get_starters(doc_id: str) -> list[StarterQuestion]:
    """Suggested opening questions, generated on first request and cached.

    An empty list is a valid answer, not an error: the reader gets a plain
    input box, which is what they had anyway. A page that cannot be opened
    because its suggestions failed would be a far worse trade.
    """
    return list(starters.generate(_require(doc_id)))


@app.post("/ask", response_model=AnswerRecord | NoteAcknowledgement)
def ask_question(request: AskRequest) -> AnswerRecord | NoteAcknowledgement:
    """Answer a question about one document, or honestly decline.

    A failure to reach the model is reported as an error, never as
    "not stated" -- conflating "we could not check" with "the document does
    not say" would be exactly the dishonesty this product exists to prevent.
    """
    doc = _require(request.doc_id)

    try:
        return handle(
            doc,
            request.question,
            history=request.history,
            corrections=request.corrections,
        )
    except AuthError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except RateLimitError as exc:
        raise HTTPException(status_code=429, detail=str(exc)) from exc
    except ChatError as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Could not reach the model, so this question was not checked. {exc}",
        ) from exc


@app.get("/health")
def health() -> dict[str, object]:
    return {"ok": True, "documents": [d.doc_id for d in list_documents()]}
