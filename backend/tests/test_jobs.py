"""The ingestion job: probe, detect, re-read, publish.

Two things are being pinned, and both are about what a paid call costs.

The first is arithmetic: a probe that guessed right must not be repeated, and a
re-upload of the same bytes must not be digitised at all. Every test here
counts digitisation calls, because the count is the behaviour.

The second is honesty. `needs_language` is a terminal state where we stop and
ask, not a failure -- and a failure to *reach* the digitiser is an error with a
reason, never a document with empty text. Publishing a blank page as if we had
read it would be the same dishonesty as answering "not stated" when we never
looked.

Nothing here touches the network.
"""

import asyncio
from pathlib import Path

import pytest

from askdoc import cache, jobs, upload
from askdoc.detect import Resolution
from askdoc.jobs import JobState, Registry, Stage
from askdoc.models import DocOrigin, LanguageSource

TAMIL = "2. இந்த வினாத்தொகுப்பு, 200 வினாக்களைக் கொண்டுள்ளது."
DEVANAGARI = "२. यह प्रश्नपत्रिका"


def resolution(**overrides) -> Resolution:
    fields = {
        "language": "ta-IN",
        "source": LanguageSource.DETECTED,
        "script": "Taml",
        "lid_language": "ta-IN",
        "needs_user": False,
        "probe_language": "hi-IN",
    }
    return Resolution(**{**fields, **overrides})


class FakeDigitiser:
    """Stands in for the paid call, honouring the same `persist` contract.

    It records the language of every call, which is what most of these tests
    actually assert on.
    """

    def __init__(self, text: str = TAMIL):
        self.text = text
        self.languages: list[str] = []

    def __call__(
        self,
        source_path,
        *,
        language: str,
        doc_id: str,
        force: bool = False,
        persist: bool = True,
        origin: DocOrigin = DocOrigin.BUILTIN,
        label: str = "",
        language_source: LanguageSource = LanguageSource.BUILTIN,
        probe_language: str = "",
    ):
        self.languages.append(language)
        doc = cache.build_doc(
            doc_id=doc_id,
            language=language,
            raw_blocks=[
                {
                    "reading_order": 1,
                    "layout_tag": "paragraph",
                    "confidence": 0.9,
                    "text": self.text,
                    "coordinates": {"x1": 0, "y1": 0, "x2": 10, "y2": 10},
                }
            ],
            source_filename=Path(source_path).name,
            origin=origin,
            label=label,
            language_source=language_source,
            probe_language=probe_language,
        )
        if persist:
            cache.save(doc)
        return doc


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    """A private cache and uploads directory, and a fresh job registry."""
    monkeypatch.setattr(cache, "CACHE_DIR", tmp_path / "cache")
    monkeypatch.setattr(upload, "UPLOADS_DIR", tmp_path / "uploads")
    monkeypatch.setattr(jobs, "REGISTRY", Registry())
    (tmp_path / "uploads").mkdir()
    source = tmp_path / "uploads" / "up_abc.png"
    source.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 2048)
    return source


def start(source, **overrides) -> str:
    fields = {"doc_id": "up_abc", "label": "scan.png"}
    job = jobs.REGISTRY.create(**{**fields, **overrides})
    return job.job_id


def run(job_id: str, source: Path) -> None:
    asyncio.run(jobs.run_ingestion(job_id, source))


class TestTheHappyPath:
    def test_a_page_in_another_language_is_read_twice(self, workspace, monkeypatch):
        digitiser = FakeDigitiser()
        monkeypatch.setattr(jobs, "digitise", digitiser)
        monkeypatch.setattr(jobs, "resolve_language", lambda *_, **__: resolution())

        job_id = start(workspace)
        run(job_id, workspace)

        assert digitiser.languages == ["hi-IN", "ta-IN"]
        job = jobs.REGISTRY.get(job_id)
        assert job.state is JobState.READY
        assert job.stage is Stage.READY
        assert job.detected_language == "ta-IN"
        assert job.script == "Taml"
        assert job.error is None

    def test_the_published_document_records_how_we_got_there(self, workspace, monkeypatch):
        monkeypatch.setattr(jobs, "digitise", FakeDigitiser())
        monkeypatch.setattr(jobs, "resolve_language", lambda *_, **__: resolution())

        run(start(workspace), workspace)

        doc = cache.load("up_abc")
        assert doc.language == "ta-IN"
        assert doc.origin is DocOrigin.UPLOAD
        assert doc.label == "scan.png"
        assert doc.language_source is LanguageSource.DETECTED
        assert doc.probe_language == "hi-IN"

    def test_a_probe_that_guessed_right_is_not_repeated(self, workspace, monkeypatch):
        # The whole point of Resolution.needs_second_pass. Digitisation is the
        # slow, paid, rate-limited step; reading the same page twice in the
        # same language buys nothing at all.
        digitiser = FakeDigitiser(DEVANAGARI)
        monkeypatch.setattr(jobs, "digitise", digitiser)
        monkeypatch.setattr(
            jobs,
            "resolve_language",
            lambda *_, **__: resolution(language="hi-IN", script="Deva", lid_language="hi-IN"),
        )

        job_id = start(workspace)
        run(job_id, workspace)

        assert digitiser.languages == ["hi-IN"]
        assert jobs.REGISTRY.get(job_id).state is JobState.READY
        assert cache.load("up_abc").language == "hi-IN"

    def test_the_probe_pass_alone_never_publishes_a_document(self, workspace, monkeypatch):
        # A page read in a language we only guessed at is not a document yet.
        seen: list[bool] = []

        def digitiser(*args, persist=True, **kwargs):
            seen.append(persist)
            return FakeDigitiser()(*args, persist=persist, **kwargs)

        monkeypatch.setattr(jobs, "digitise", digitiser)
        monkeypatch.setattr(jobs, "resolve_language", lambda *_, **__: resolution())

        run(start(workspace), workspace)

        assert seen == [False, True]


class TestNeedsLanguageIsNotAFailure:
    @pytest.fixture
    def ambiguous(self, workspace, monkeypatch):
        monkeypatch.setattr(jobs, "digitise", FakeDigitiser(DEVANAGARI))
        monkeypatch.setattr(
            jobs,
            "resolve_language",
            lambda *_, **__: resolution(
                language=None,
                source=LanguageSource.USER,
                script="Deva",
                lid_language="hi-IN",
                needs_user=True,
            ),
        )
        job_id = start(workspace)
        run(job_id, workspace)
        return jobs.REGISTRY.get(job_id)

    def test_it_is_terminal_and_carries_no_error(self, ambiguous):
        assert ambiguous.state is JobState.NEEDS_LANGUAGE
        assert ambiguous.stage is Stage.NEEDS_LANGUAGE
        assert ambiguous.error is None

    def test_it_offers_what_lid_thought_without_acting_on_it(self, ambiguous):
        assert ambiguous.script == "Deva"
        assert ambiguous.detected_language == "hi-IN"

    def test_nothing_is_published_until_the_reader_answers(self, ambiguous):
        assert cache.load("up_abc") is None

    def test_the_probe_text_is_kept_so_the_reader_does_not_wait_twice(self, ambiguous):
        assert ambiguous.probe is not None
        assert ambiguous.probe.language == "hi-IN"


class TestFailuresAreReportedAsFailures:
    @pytest.mark.parametrize(
        "error,expected",
        [
            (jobs.DigitisationError("empty text"), jobs.COULD_NOT_READ),
            (jobs.RateLimitError("429"), jobs.SERVICE_BUSY),
            (jobs.AuthError("403"), jobs.SERVICE_REJECTED),
            (jobs.ChatError("connection refused"), jobs.SERVICE_UNREACHABLE),
            (RuntimeError("something nobody anticipated"), jobs.UNEXPECTED),
        ],
    )
    def test_each_cause_gets_its_own_plain_language_reason(
        self, workspace, monkeypatch, error, expected
    ):
        def boom(*_, **__):
            raise error

        monkeypatch.setattr(jobs, "digitise", boom)

        job_id = start(workspace)
        run(job_id, workspace)

        job = jobs.REGISTRY.get(job_id)
        assert job.state is JobState.FAILED
        assert job.stage is Stage.FAILED
        assert job.error == expected

    def test_a_partially_completed_job_caches_nothing(self, workspace, monkeypatch):
        # PartiallyCompleted reaches us as a DigitisationError. Half a page
        # cached is worse than none: "not stated" would then mean "not stated
        # in the half I got", which is a different and dishonest claim.
        def boom(*_, **__):
            raise jobs.DigitisationError("finished in state 'PartiallyCompleted'")

        monkeypatch.setattr(jobs, "digitise", boom)
        run(start(workspace), workspace)

        assert cache.load("up_abc") is None

    def test_a_failure_on_the_second_pass_still_caches_nothing(self, workspace, monkeypatch):
        digitiser = FakeDigitiser()

        def fail_second(*args, **kwargs):
            if digitiser.languages:
                raise jobs.DigitisationError("second pass failed")
            return digitiser(*args, **kwargs)

        monkeypatch.setattr(jobs, "digitise", fail_second)
        monkeypatch.setattr(jobs, "resolve_language", lambda *_, **__: resolution())

        job_id = start(workspace)
        run(job_id, workspace)

        assert jobs.REGISTRY.get(job_id).state is JobState.FAILED
        assert cache.load("up_abc") is None

    def test_detection_failing_does_not_lose_the_document(self, workspace, monkeypatch):
        # resolve_language absorbs a LID outage itself; anything that escapes
        # it is a real fault and must be reported, not guessed around.
        monkeypatch.setattr(jobs, "digitise", FakeDigitiser())

        def boom(*_, **__):
            raise jobs.AuthError("403")

        monkeypatch.setattr(jobs, "resolve_language", boom)

        job_id = start(workspace)
        run(job_id, workspace)

        assert jobs.REGISTRY.get(job_id).error == jobs.SERVICE_REJECTED


class TestTheLanguageOverride:
    def test_it_re_reads_the_stored_original(self, workspace, monkeypatch):
        digitiser = FakeDigitiser()
        monkeypatch.setattr(jobs, "digitise", digitiser)

        job_id = start(workspace, stage=Stage.DIGITISING_FINAL)
        asyncio.run(jobs.run_language_override(job_id, workspace, "mr-IN"))

        assert digitiser.languages == ["mr-IN"]
        doc = cache.load("up_abc")
        assert doc.language == "mr-IN"
        assert doc.language_source is LanguageSource.USER
        assert jobs.REGISTRY.get(job_id).state is JobState.READY

    def test_choosing_the_probe_language_costs_nothing(self, workspace, monkeypatch):
        # The ambiguous case is Devanagari, and the probe is hi-IN -- so the
        # single commonest answer to the picker is a page we have already read.
        digitiser = FakeDigitiser(DEVANAGARI)
        monkeypatch.setattr(jobs, "digitise", digitiser)
        monkeypatch.setattr(
            jobs,
            "resolve_language",
            lambda *_, **__: resolution(
                language=None, source=LanguageSource.USER, script="Deva", needs_user=True
            ),
        )
        first = start(workspace)
        run(first, workspace)
        digitiser.languages.clear()

        second = jobs.REGISTRY.create(
            doc_id="up_abc", label="scan.png", probe=jobs.REGISTRY.get(first).probe
        )
        asyncio.run(jobs.run_language_override(second.job_id, workspace, "hi-IN"))

        assert digitiser.languages == []
        doc = cache.load("up_abc")
        assert doc.language == "hi-IN"
        assert doc.language_source is LanguageSource.USER

    def test_a_failed_re_read_reports_the_failure(self, workspace, monkeypatch):
        def boom(*_, **__):
            raise jobs.DigitisationError("nope")

        monkeypatch.setattr(jobs, "digitise", boom)

        job_id = start(workspace)
        asyncio.run(jobs.run_language_override(job_id, workspace, "mr-IN"))

        assert jobs.REGISTRY.get(job_id).error == jobs.COULD_NOT_READ


class TestTheRegistry:
    def test_updates_replace_rather_than_mutate(self, workspace):
        job = jobs.REGISTRY.create(doc_id="up_abc", label="scan.png")
        updated = jobs.REGISTRY.update(job.job_id, stage=Stage.DETECTING)

        assert job.stage is Stage.VALIDATING
        assert updated.stage is Stage.DETECTING
        assert jobs.REGISTRY.get(job.job_id).stage is Stage.DETECTING

    def test_unknown_jobs_are_absent_rather_than_invented(self, workspace):
        assert jobs.REGISTRY.get("job_nope") is None

    def test_the_latest_job_for_a_document_is_the_one_that_counts(self, workspace):
        first = jobs.REGISTRY.create(doc_id="up_abc", label="a")
        second = jobs.REGISTRY.create(doc_id="up_abc", label="b")

        assert jobs.REGISTRY.latest_for("up_abc").job_id == second.job_id
        assert first.job_id != second.job_id


class TestFindingTheStoredOriginal:
    def test_it_finds_the_kept_bytes(self, workspace):
        assert jobs.stored_source("up_abc") == workspace

    def test_a_document_we_never_stored_has_none(self, workspace):
        assert jobs.stored_source("doc_a") is None

    @pytest.mark.parametrize("doc_id", ["../cache/doc_a", "/etc/passwd", "..", "a/b"])
    def test_an_id_that_escapes_the_uploads_directory_is_refused(self, workspace, doc_id):
        assert jobs.stored_source(doc_id) is None
