"""Ingesting a reader's own page: probe, detect, re-read, publish.

Digitisation has no auto-detect and `language` is mandatory, so reading an
uploaded page is a small state machine rather than one call. We probe in
`config.PROBE_LANGUAGE`, read the script off what comes back, and re-read only
when the guess was wrong -- `Resolution.needs_second_pass` decides that, so the
rule lives in exactly one place.

Two things here are load-bearing:

* **`needs_language` is a terminal state, not an error.** A script that carries
  eight languages is one we honestly cannot name, so we stop and ask. The probe
  text is kept on the job, because the reader's most likely answer to a
  Devanagari page is Hindi -- which is what we already read it as.
* **A failure to reach the digitiser is reported as a failure.** Nothing is
  cached, and no half-read page is published. A document whose text is missing
  because a call failed would answer "not stated" about things the page states,
  which is the one thing this product exists to prevent.

The registry below is the only server-side state in the backend. It is not a
walk-back of "the backend stores nothing between requests" -- that invariant is
about *session* state (history, corrections, what you asked), all of which
still lives on the client. A job is transient plumbing for one upload;
finished documents live on disk. A restart loses in-flight uploads and nothing
else.
"""

from __future__ import annotations

import threading
import uuid
from datetime import datetime, timezone
from enum import Enum
from functools import partial
from pathlib import Path

from anyio import to_thread
from pydantic import Field

from . import cache, upload
from .config import PROBE_LANGUAGE
from .detect import resolve_language
from .digitise import DigitisationError, digitise
from .models import DigitisedDoc, DocOrigin, Frozen, LanguageSource
from .sarvam_http import AuthError, ChatError, RateLimitError


class JobState(str, Enum):
    """The authoritative field. `stage` narrates; `state` decides.

    A client that reads only this knows everything it has to do next: keep
    polling, open the document, show the picker, or show the error.
    """

    RUNNING = "running"
    READY = "ready"
    FAILED = "failed"
    NEEDS_LANGUAGE = "needs_language"


class Stage(str, Enum):
    """Where in the machine we are, for the reader's progress line.

    The last three mirror the terminal `JobState` values exactly, so the two
    fields can never disagree about whether a job is done.
    """

    VALIDATING = "validating"
    DIGITISING_PROBE = "digitising_probe"
    DETECTING = "detecting"
    DIGITISING_FINAL = "digitising_final"
    READY = "ready"
    FAILED = "failed"
    NEEDS_LANGUAGE = "needs_language"


# --- product copy ------------------------------------------------------------
#
# Shown to the reader verbatim. Each names a different thing that went wrong,
# because "your scan is unreadable" and "we could not reach the service" call
# for different next steps and only one of them is about their file.

COULD_NOT_READ = (
    "I couldn't read this page — the digitiser didn't return usable text. "
    "Try a clearer scan or photo."
)
SERVICE_BUSY = (
    "The reading service is busy right now. Wait a minute and try again — "
    "nothing was lost."
)
SERVICE_UNREACHABLE = (
    "I couldn't reach the reading service, so this page hasn't been read. "
    "Nothing was saved. Try again in a moment."
)
# Deliberately promises nothing. A rejected key is fixed by whoever runs this,
# not by the reader, and "try again" would only cost them their time.
SERVICE_REJECTED = (
    "The reading service turned us away, so this page hasn't been read. "
    "That's a problem at our end, not with your file."
)
UNEXPECTED = "Something went wrong reading this page. Nothing was saved — try again."


class Job(Frozen):
    """One ingestion, from upload to a document on disk.

    `doc_id` is set from the content hash before any work starts, so it is
    known in every state including `needs_language` -- the picker posts to
    `/documents/{doc_id}/language`, and a state the reader cannot answer would
    be a dead end.
    """

    job_id: str
    doc_id: str
    label: str = ""
    state: JobState = JobState.RUNNING
    stage: Stage = Stage.VALIDATING
    detected_language: str | None = None
    script: str = ""
    language_source: LanguageSource | None = None
    error: str | None = None
    created_at: str = ""

    # The probe pass, held only until the reader answers the picker. Excluded
    # from serialisation: it is a paid call we are hanging onto so they are not
    # made to wait twice, not part of the job's public shape. It is
    # deliberately NOT cached -- a page read in a language we only guessed at
    # is not a document yet, and listing it as one would invite questions
    # against text we already know may be garbled.
    probe: DigitisedDoc | None = Field(default=None, exclude=True)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Registry:
    """In-memory job table. A dict and a lock; nothing survives a restart.

    Jobs are replaced rather than mutated, so a caller holding a Job holds the
    state it observed and not one that changed underneath it.
    """

    def __init__(self) -> None:
        self._jobs: dict[str, Job] = {}
        self._lock = threading.Lock()

    def create(self, **fields) -> Job:
        job = Job(job_id=f"job_{uuid.uuid4().hex[:16]}", created_at=_now(), **fields)
        with self._lock:
            self._jobs[job.job_id] = job
        return job

    def get(self, job_id: str) -> Job | None:
        with self._lock:
            return self._jobs.get(job_id)

    def update(self, job_id: str, **fields) -> Job:
        with self._lock:
            job = self._jobs[job_id].model_copy(update=fields)
            self._jobs[job_id] = job
            return job

    def latest_for(self, doc_id: str) -> Job | None:
        """The most recent job for a document, so a language override can
        inherit the probe text the run before it paid for.

        Ordered by insertion rather than by `created_at`: two jobs for the same
        upload land well inside one second, and a timestamp that cannot tell
        them apart would hand back the wrong one.
        """
        with self._lock:
            jobs = list(self._jobs.values())
        return next((j for j in reversed(jobs) if j.doc_id == doc_id), None)


REGISTRY = Registry()


def stored_source(doc_id: str) -> Path | None:
    """The original bytes kept for `doc_id`, if they are still on disk.

    `doc_id` reaches this from a URL path, so the resolved path is checked to
    be inside the uploads directory rather than the id being pattern-matched:
    containment is the property we actually need, and it cannot drift out of
    step with the way the filename is built.
    """
    root = upload.UPLOADS_DIR.resolve()
    for kind in ("pdf", "png", "jpeg"):
        path = (upload.UPLOADS_DIR / f"{doc_id}.{kind}").resolve()
        if path.is_relative_to(root) and path.is_file():
            return path
    return None


def _reason_for(error: Exception) -> str:
    """The reader's words for what went wrong.

    Each cause gets its own, because they call for different next steps: a
    clearer scan, a minute's wait, or nothing they can do at all. Collapsing
    them into one message would tell someone to retry a page that will never
    work, or blame their file for our expired key.
    """
    if isinstance(error, DigitisationError):
        return COULD_NOT_READ
    if isinstance(error, RateLimitError):
        return SERVICE_BUSY
    if isinstance(error, AuthError):
        return SERVICE_REJECTED
    if isinstance(error, ChatError):
        return SERVICE_UNREACHABLE
    return UNEXPECTED


def _fail(job_id: str, error: Exception) -> None:
    REGISTRY.update(
        job_id,
        state=JobState.FAILED,
        stage=Stage.FAILED,
        error=_reason_for(error),
    )


async def _in_thread(func, *args, **kwargs):
    """Run a blocking call off the event loop.

    Digitisation is a minutes-long HTTP poll and detection is a network call.
    Either one on the loop would stall every other reader's questions.
    """
    return await to_thread.run_sync(partial(func, *args, **kwargs))


def _publish(doc: DigitisedDoc, language_source: LanguageSource) -> DigitisedDoc:
    """Save a document, recording on whose authority its language was set."""
    published = doc.model_copy(update={"language_source": language_source})
    cache.save(published)
    return published


async def run_ingestion(job_id: str, source: Path) -> None:
    """Read an uploaded page, working out its language on the way.

    Never raises: a job that fails says so in its own record, because the
    caller is a background task with nobody left to catch it.
    """
    job = REGISTRY.get(job_id)
    if job is None:  # the registry was reset under us; nothing to report to
        return

    read = partial(
        _in_thread,
        digitise,
        source,
        doc_id=job.doc_id,
        origin=DocOrigin.UPLOAD,
        label=job.label,
        probe_language=PROBE_LANGUAGE,
        force=True,
    )

    try:
        REGISTRY.update(job_id, stage=Stage.DIGITISING_PROBE)
        # persist=False: the probe is a guess, and a guess does not get to be a
        # document. Only the pass whose language we can defend is cached.
        probe = await read(language=PROBE_LANGUAGE, persist=False)

        REGISTRY.update(job_id, stage=Stage.DETECTING)
        resolution = await _in_thread(resolve_language, probe, probe_language=PROBE_LANGUAGE)

        if resolution.needs_user:
            # Terminal, and not a failure: the script carries several languages
            # or none we know, so we stop and ask rather than silently reading
            # an Urdu page as Hindi.
            REGISTRY.update(
                job_id,
                state=JobState.NEEDS_LANGUAGE,
                stage=Stage.NEEDS_LANGUAGE,
                script=resolution.script,
                detected_language=resolution.lid_language,
                probe=probe,
            )
            return

        if resolution.needs_second_pass:
            REGISTRY.update(job_id, stage=Stage.DIGITISING_FINAL, script=resolution.script)
            doc = await read(language=resolution.language, language_source=resolution.source)
        else:
            doc = _publish(probe, resolution.source)
    except Exception as exc:  # noqa: BLE001 -- see _reason_for; every path reports
        _fail(job_id, exc)
        return

    REGISTRY.update(
        job_id,
        state=JobState.READY,
        stage=Stage.READY,
        detected_language=doc.language,
        script=resolution.script,
        language_source=doc.language_source,
        probe=None,
    )


async def run_language_override(job_id: str, source: Path, language: str) -> None:
    """Re-read a page in the language the reader named.

    The probe pass is reused when it already used this language. That is not a
    rare shortcut: the picker only appears for scripts like Devanagari, and the
    probe language is Hindi -- so the commonest answer to the question is a
    page we have already paid to read.
    """
    job = REGISTRY.get(job_id)
    if job is None:
        return

    try:
        REGISTRY.update(job_id, stage=Stage.DIGITISING_FINAL)
        if job.probe is not None and job.probe.language == language:
            doc = _publish(job.probe, LanguageSource.USER)
        else:
            doc = await _in_thread(
                digitise,
                source,
                language=language,
                doc_id=job.doc_id,
                origin=DocOrigin.UPLOAD,
                label=job.label,
                language_source=LanguageSource.USER,
                probe_language=PROBE_LANGUAGE,
                force=True,
            )
    except Exception as exc:  # noqa: BLE001
        _fail(job_id, exc)
        return

    REGISTRY.update(
        job_id,
        state=JobState.READY,
        stage=Stage.READY,
        detected_language=doc.language,
        language_source=LanguageSource.USER,
        probe=None,
    )
