"""Language detection: LID proposes, our own Unicode-block count disposes.

The property under test is the same one the citation gate protects, applied to
detection instead of quoting. `/text-lid` knows 11 languages; digitisation
accepts 23, so LID cannot name Urdu or Assamese and will answer with one of its
own 11 rather than admit that. A verdict we cannot check is not trusted, and
where we genuinely cannot tell we ask the reader instead of guessing.

Nothing here touches the network -- the LID call is always mocked.
"""

import httpx
import pytest

from askdoc import cache, detect
from askdoc.config import LID_MAX_CHARS
from askdoc.config import SUPPORTED_LANGUAGES
from askdoc.detect import (
    AMBIGUOUS_SCRIPTS,
    SCRIPT_LANGUAGES,
    SCRIPT_TO_LANGUAGE,
    LidResult,
    dominant_script,
    identify_language,
    resolve_language,
    sample_for_lid,
)
from askdoc.models import LanguageSource
from askdoc.sarvam_http import AuthError, ChatError, RateLimitError

TAMIL = "இந்த வினாத்தொகுப்பு, 200 வினாக்களைக் கொண்டுள்ளது."
TELUGU = "దరఖాస్తు రుసుము ఎంత? చివరి తేదీ 30-08-2025."
DEVANAGARI = "यह एक सरकारी सूचना है। अंतिम तिथि 30 अगस्त है।"
LATIN = "Government of India -- Notification No. 14 of 2025."
URDU = "یہ ایک سرکاری اطلاع ہے۔"
BENGALI = "এই বিজ্ঞপ্তি সরকারি। শেষ তারিখ ৩০ আগস্ট।"
ASSAMESE = "এই বিজ্ঞপ্তিৰ শেষ তাৰিখ ৩০ আগষ্ট।"  # ৰ is Assamese, not Bengali
GUJARATI = "આ સરકારી સૂચના છે. છેલ્લી તારીખ ૩૦ ઓગસ્ટ."
GURMUKHI = "ਇਹ ਸਰਕਾਰੀ ਸੂਚਨਾ ਹੈ। ਆਖਰੀ ਮਿਤੀ ੩੦ ਅਗਸਤ।"


def build_doc(*texts: str, doc_id: str = "up_test"):
    """A DigitisedDoc with one block per argument, in the order given."""
    return cache.build_doc(
        doc_id=doc_id,
        language="hi-IN",
        raw_blocks=[
            {
                "reading_order": index,
                "layout_tag": "paragraph",
                "confidence": 0.9,
                "text": text,
                "coordinates": {"x1": 0, "y1": 0, "x2": 10, "y2": 10},
            }
            for index, text in enumerate(texts, start=1)
        ],
        source_filename="upload.pdf",
    )


class FakeResponse:
    def __init__(self, status_code=200, payload=None, text=""):
        self.status_code = status_code
        self._payload = payload
        self.text = text

    def json(self):
        if self._payload is None:
            raise ValueError("not JSON")
        return self._payload


@pytest.fixture(autouse=True)
def api_key(monkeypatch):
    monkeypatch.setenv("SARVAM_API_KEY", "test-key")


@pytest.fixture
def lid(monkeypatch):
    """Capture the LID request and control its reply."""
    calls: list[dict] = []

    def install(response=None, error=None):
        def fake_post(url, **kwargs):
            calls.append({"url": url, **kwargs})
            if error is not None:
                raise error
            return response

        monkeypatch.setattr(detect.httpx, "post", fake_post)
        return calls

    return install


class TestDominantScript:
    @pytest.mark.parametrize(
        ("text", "expected"),
        [
            (TAMIL, "Taml"),
            (TELUGU, "Telu"),
            (DEVANAGARI, "Deva"),
            (LATIN, "Latn"),
            (URDU, "Arab"),
        ],
    )
    def test_real_pages_are_identified(self, text, expected):
        assert dominant_script(text) == expected

    def test_a_bilingual_page_reports_its_majority_script(self):
        assert dominant_script(f"APPLICATION FORM\n{TAMIL}\n{TAMIL}") == "Taml"

    @pytest.mark.parametrize(
        "text",
        ["", "   \n\t  ", "2026-07-26 :: 200 (10) -- 45%", "।॥"],
    )
    def test_nothing_to_count_is_undetermined(self, text):
        # Digits, punctuation and whitespace are not evidence of a language,
        # so a page of only those must not resolve to whatever script their
        # codepoints happen to sit near.
        assert dominant_script(text) == "Zyyy"

    def test_an_unsupported_script_is_undetermined_rather_than_guessed(self):
        assert dominant_script("Ελληνικά κείμενο εδώ") == "Zyyy"

    def test_line_numbers_and_table_pipes_do_not_vote(self):
        assert dominant_script(f" 17 | {TELUGU} | 64 | 09 |") == "Telu"


class TestSampleForLid:
    def test_the_longest_block_wins_not_the_first(self):
        # A bilingual government form opens with an English header. Sampling
        # the first block would report en-IN for a Tamil page.
        doc = build_doc("APPLICATION FORM", TAMIL * 3)
        assert dominant_script(sample_for_lid(doc)) == "Taml"

    def test_the_sample_is_capped(self):
        doc = build_doc(TAMIL * 200)
        assert len(sample_for_lid(doc)) <= LID_MAX_CHARS

    def test_a_document_without_blocks_still_yields_a_sample(self):
        doc = build_doc().model_copy(update={"text": TELUGU})
        assert TELUGU in sample_for_lid(doc)


class TestIdentifyLanguage:
    def test_a_verdict_is_parsed(self, lid):
        lid(FakeResponse(payload={"language_code": "ta-IN", "script_code": "Taml"}))
        assert identify_language(TAMIL) == LidResult(language_code="ta-IN", script_code="Taml")

    def test_the_request_matches_the_documented_contract(self, lid):
        calls = lid(FakeResponse(payload={"language_code": "ta-IN", "script_code": "Taml"}))
        identify_language(TAMIL)
        assert calls[0]["url"] == detect.LID_URL
        assert calls[0]["json"] == {"input": TAMIL}
        assert calls[0]["headers"]["api-subscription-key"] == "test-key"

    def test_oversized_input_is_trimmed_rather_than_rejected(self, lid):
        calls = lid(FakeResponse(payload={"language_code": "ta-IN", "script_code": "Taml"}))
        identify_language("அ" * (LID_MAX_CHARS * 2))
        assert len(calls[0]["json"]["input"]) == LID_MAX_CHARS

    def test_missing_fields_are_absences_not_crashes(self, lid):
        lid(FakeResponse(payload={"request_id": "abc"}))
        assert identify_language(TAMIL) == LidResult()

    @pytest.mark.parametrize(
        ("status", "expected"),
        [(403, AuthError), (429, RateLimitError), (500, ChatError)],
    )
    def test_failures_are_typed(self, lid, status, expected):
        lid(FakeResponse(status_code=status, text="nope"))
        with pytest.raises(expected):
            identify_language(TAMIL)

    def test_an_unreachable_service_is_a_chat_error(self, lid):
        lid(error=httpx.ConnectError("no route"))
        with pytest.raises(ChatError):
            identify_language(TAMIL)

    def test_a_non_json_body_is_a_chat_error(self, lid):
        lid(FakeResponse(payload=None, text="<html>"))
        with pytest.raises(ChatError):
            identify_language(TAMIL)


class TestResolution:
    def test_lid_agreeing_with_the_script_is_trusted(self, lid):
        lid(FakeResponse(payload={"language_code": "ta-IN", "script_code": "Taml"}))
        result = resolve_language(build_doc(TAMIL), probe_language="hi-IN")
        assert (result.language, result.source) == ("ta-IN", LanguageSource.DETECTED)
        assert result.needs_user is False

    def test_a_one_to_one_script_overrules_a_disagreeing_lid(self, lid):
        # LID has no Tamil-shaped answer for a page it misread; our own count
        # of the codepoints does, and it is the checkable one.
        lid(FakeResponse(payload={"language_code": "hi-IN", "script_code": "Deva"}))
        result = resolve_language(build_doc(TAMIL), probe_language="hi-IN")
        assert (result.language, result.source) == ("ta-IN", LanguageSource.SCRIPT)
        assert result.lid_language == "hi-IN"
        assert result.needs_user is False

    def test_a_language_we_cannot_digitise_in_is_not_adopted(self, lid):
        lid(FakeResponse(payload={"language_code": "fr-FR", "script_code": "Latn"}))
        result = resolve_language(build_doc(LATIN), probe_language="hi-IN")
        assert (result.language, result.source) == ("en-IN", LanguageSource.SCRIPT)

    def test_an_unrecognised_script_asks_the_reader(self, lid):
        lid(FakeResponse(payload={"language_code": "en-IN", "script_code": "Latn"}))
        result = resolve_language(build_doc("Ελληνικά"), probe_language="hi-IN")
        assert (result.script, result.needs_user) == ("Zyyy", True)
        assert result.source is LanguageSource.USER

    def test_ambiguity_is_disjoint_from_the_one_to_one_map(self):
        # The two constants must not overlap, or an ambiguous script would
        # acquire a language by lookup.
        assert AMBIGUOUS_SCRIPTS.isdisjoint(SCRIPT_TO_LANGUAGE)

    def test_every_ambiguous_script_lists_the_languages_it_carries(self):
        # Without an entry an ambiguous script could never accept a verdict,
        # so its readers would be sent to the picker unconditionally.
        assert set(SCRIPT_LANGUAGES) == set(AMBIGUOUS_SCRIPTS)

    def test_the_listed_languages_are_ones_we_can_digitise_in(self):
        for languages in SCRIPT_LANGUAGES.values():
            assert languages <= set(SUPPORTED_LANGUAGES)


class TestAmbiguousScripts:
    """The script names nothing on its own, so LID is checked against it."""

    @pytest.mark.parametrize("language", ["hi-IN", "mr-IN"])
    def test_a_language_written_in_that_script_is_accepted(self, lid, language):
        # LID genuinely knows Hindi from Marathi, and Hindi is the likeliest
        # upload of all -- sending every Hindi reader to a picker would refuse
        # the one thing LID is actually better at than we are.
        lid(FakeResponse(payload={"language_code": language, "script_code": "Deva"}))
        result = resolve_language(build_doc(DEVANAGARI), probe_language="hi-IN")
        assert (result.language, result.source) == (language, LanguageSource.DETECTED)
        assert result.needs_user is False

    def test_urdu_is_accepted_on_the_arabic_script(self, lid):
        lid(FakeResponse(payload={"language_code": "ur-IN", "script_code": "Arab"}))
        result = resolve_language(build_doc(URDU), probe_language="hi-IN")
        assert (result.language, result.source) == ("ur-IN", LanguageSource.DETECTED)

    def test_a_language_not_written_in_that_script_is_refused(self, lid):
        # Tamil is not written in Devanagari, so this contradicts what we can
        # see. A verdict we can check and that fails is worth less than none.
        lid(FakeResponse(payload={"language_code": "ta-IN", "script_code": "Taml"}))
        result = resolve_language(build_doc(DEVANAGARI), probe_language="hi-IN")
        assert result.needs_user is True
        assert result.language is None
        assert result.source is LanguageSource.USER
        assert result.script == "Deva"
        assert result.lid_language == "ta-IN"  # offered as the picker's default

    def test_urdu_is_never_silently_read_as_hindi(self, lid):
        # LID has no Urdu in its eleven, so it answers with the nearest thing
        # it does have. This is the misread the whole check exists to stop.
        lid(FakeResponse(payload={"language_code": "hi-IN", "script_code": "Deva"}))
        result = resolve_language(build_doc(URDU), probe_language="hi-IN")
        assert result.needs_user is True
        assert result.language is None

    def test_an_empty_verdict_asks_the_reader(self, lid):
        lid(FakeResponse(payload={"request_id": "abc"}))
        assert resolve_language(build_doc(DEVANAGARI), probe_language="hi-IN").needs_user


class TestSharedScriptsAreSeparatedByOrthography:
    """Bengali script carries Assamese too, and LID cannot name Assamese at all."""

    def test_assamese_letters_resolve_to_assamese(self, lid):
        lid(FakeResponse(payload={"language_code": "bn-IN", "script_code": "Beng"}))
        result = resolve_language(build_doc(ASSAMESE), probe_language="hi-IN")
        assert (result.language, result.source) == ("as-IN", LanguageSource.SCRIPT)
        assert result.needs_user is False

    def test_bengali_without_them_stays_bengali(self, lid):
        lid(FakeResponse(payload={"language_code": "bn-IN", "script_code": "Beng"}))
        result = resolve_language(build_doc(BENGALI), probe_language="hi-IN")
        assert result.language == "bn-IN"

    def test_character_evidence_outranks_lid(self, lid):
        # LID's eleven do not include Assamese, so agreeing with it here would
        # be the same silent misread, arrived at more politely.
        lid(FakeResponse(payload={"language_code": "bn-IN", "script_code": "Beng"}))
        assert resolve_language(build_doc(ASSAMESE), probe_language="hi-IN").language == "as-IN"

    def test_the_evidence_survives_an_outage(self, lid):
        lid(error=ChatError("down"))
        assert resolve_language(build_doc(ASSAMESE), probe_language="hi-IN").language == "as-IN"

    @pytest.mark.parametrize(
        ("text", "expected"),
        [(GUJARATI, "gu-IN"), (GURMUKHI, "pa-IN")],
    )
    def test_scripts_that_really_do_name_one_language(self, lid, text, expected):
        # Gujarati and Gurmukhi each carry exactly one of the 23, so there is
        # no refinement to invent here.
        lid(error=ChatError("down"))
        assert resolve_language(build_doc(text), probe_language="hi-IN").language == expected


class TestLidOutageIsNotFatal:
    """Losing detection must never lose the document."""

    @pytest.mark.parametrize(
        "error",
        [ChatError("down"), AuthError("bad key"), RateLimitError("429")],
    )
    def test_the_script_still_decides(self, lid, error):
        lid(error=error)
        result = resolve_language(build_doc(TELUGU), probe_language="hi-IN")
        assert (result.language, result.source) == ("te-IN", LanguageSource.SCRIPT)
        assert result.lid_language is None
        assert result.needs_user is False

    def test_an_outage_on_an_ambiguous_script_still_asks_rather_than_guesses(self, lid):
        # The probe language was hi-IN and the page is Devanagari, which makes
        # Hindi a tempting default. It is still a guess, so it is not made.
        lid(error=ChatError("down"))
        result = resolve_language(build_doc(DEVANAGARI), probe_language="hi-IN")
        assert result.needs_user is True
        assert result.language is None


class TestSecondPass:
    """The paid re-digitisation is skipped when the probe already got it right."""

    def test_a_different_language_needs_another_pass(self, lid):
        lid(FakeResponse(payload={"language_code": "ta-IN", "script_code": "Taml"}))
        assert resolve_language(build_doc(TAMIL), probe_language="hi-IN").needs_second_pass

    def test_the_probe_language_is_kept(self, lid):
        lid(FakeResponse(payload={"language_code": "ta-IN", "script_code": "Taml"}))
        result = resolve_language(build_doc(DEVANAGARI), probe_language="hi-IN")
        assert result.probe_language == "hi-IN"
        assert result.needs_second_pass is False  # nothing resolved yet to re-run with

    def test_a_detected_ambiguous_language_matching_the_probe_is_not_repeated(self, lid):
        lid(FakeResponse(payload={"language_code": "hi-IN", "script_code": "Deva"}))
        result = resolve_language(build_doc(DEVANAGARI), probe_language="hi-IN")
        assert (result.language, result.needs_second_pass) == ("hi-IN", False)

    def test_a_correct_probe_is_not_repeated(self, lid):
        lid(FakeResponse(payload={"language_code": "ta-IN", "script_code": "Taml"}))
        assert not resolve_language(build_doc(TAMIL), probe_language="ta-IN").needs_second_pass
