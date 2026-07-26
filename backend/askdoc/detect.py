"""What language is this page in?

Digitisation has no auto-detect, so an upload is probed in one language, read
back, and only then identified. Sarvam's `/text-lid` does the identifying --
but it covers **11** languages while digitisation accepts **23**. It cannot
name Assamese, Urdu, Sanskrit, Santali or Manipuri, and rather than say so it
answers with the nearest of its own eleven.

So LID proposes and a deterministic Unicode-block count disposes. This is the
same shape as the citation gate: the model points, we check, and where we
cannot check we decline to claim. On a script that carries many languages
(Devanagari, Arabic) the count cannot name the language by itself, so LID is
taken at its word -- but only when it names a language actually written in the
script we can see. That accepts "Devanagari, and LID says Hindi" and refuses
"Arabic, and LID says Hindi", which is how an Urdu page avoids being silently
read as Hindi. When the check fails there is no fallback guess: we ask.

Detection is deliberately confined to this module. If the probe assumption in
`config.PROBE_LANGUAGE` turns out not to hold, `resolve_language` is the only
thing that has to change.
"""

from __future__ import annotations

from collections import Counter

import httpx

from .config import LID_MAX_CHARS, SUPPORTED_LANGUAGES, api_key
from .models import DigitisedDoc, Frozen, LanguageSource
from .sarvam_http import AuthError, ChatError, RateLimitError

LID_URL = "https://api.sarvam.ai/text-lid"

# LID returns a couple of fields; 90s is for chat completions, not this.
LID_TIMEOUT = 15.0

# ISO 15924 for "undetermined". Returned when there is nothing countable on the
# page, or when what is there belongs to no script we can digitise.
UNDETERMINED = "Zyyy"

# Scripts that name one of the languages digitisation accepts. Seeing the
# script IS the answer here, which is why it can overrule LID.
#
# Beng is the one entry that is not strictly 1:1 -- Assamese shares it -- so it
# names the majority reading and `_orthographic_language` refines it on
# character evidence before this map is consulted.
SCRIPT_TO_LANGUAGE = {
    "Taml": "ta-IN",
    "Telu": "te-IN",
    "Knda": "kn-IN",
    "Mlym": "ml-IN",
    "Beng": "bn-IN",
    "Gujr": "gu-IN",
    "Orya": "od-IN",
    "Guru": "pa-IN",
    "Olck": "sat-IN",
    "Mtei": "mni-IN",
    "Latn": "en-IN",
}

# Scripts shared by many supported languages. The script alone cannot name the
# language, so it is LID or the reader -- never a guess of ours.
AMBIGUOUS_SCRIPTS = frozenset({"Deva", "Arab"})

# Which supported languages each ambiguous script is actually written in.
#
# This is what makes LID's verdict checkable on a script that names nothing by
# itself: naming hi-IN for a Devanagari page is a real claim about the language
# and is accepted, while naming ta-IN for one is a contradiction of what we can
# see and sends us to the reader. LID knows two of the eight Devanagari
# languages and none of the Arabic ones, so most of these entries exist to be
# *failed*, not matched.
SCRIPT_LANGUAGES = {
    "Deva": frozenset({"hi-IN", "mr-IN", "sa-IN", "ne-IN", "kok-IN", "mai-IN", "doi-IN", "brx-IN"}),
    "Arab": frozenset({"ur-IN", "ks-IN", "sd-IN"}),
}

# Letters Assamese uses and Bengali does not: ra (U+09F0) and wa (U+09F1).
# Their presence is positive, deterministic evidence of a language LID cannot
# name at all -- so it outranks LID rather than being overridden by it.
ASSAMESE_LETTERS = ("ৰ", "ৱ")

# Codepoint ranges, checked in order. Only the blocks that map to a language we
# can digitise are listed: a page in Greek or Cyrillic must come out as
# UNDETERMINED rather than as the nearest thing we happen to recognise.
_SCRIPT_RANGES: tuple[tuple[int, int, str], ...] = (
    (0x0041, 0x005A, "Latn"),
    (0x0061, 0x007A, "Latn"),
    (0x00C0, 0x024F, "Latn"),
    (0x0600, 0x06FF, "Arab"),
    (0x0750, 0x077F, "Arab"),
    (0x08A0, 0x08FF, "Arab"),
    (0x0900, 0x097F, "Deva"),
    (0x0980, 0x09FF, "Beng"),
    (0x0A00, 0x0A7F, "Guru"),
    (0x0A80, 0x0AFF, "Gujr"),
    (0x0B00, 0x0B7F, "Orya"),
    (0x0B80, 0x0BFF, "Taml"),
    (0x0C00, 0x0C7F, "Telu"),
    (0x0C80, 0x0CFF, "Knda"),
    (0x0D00, 0x0D7F, "Mlym"),
    (0x1C50, 0x1C7F, "Olck"),
    (0xA8E0, 0xA8FF, "Deva"),  # Devanagari Extended
    (0xAAE0, 0xAAFF, "Mtei"),  # Meetei Mayek Extensions
    (0xABC0, 0xABFF, "Mtei"),
    (0xFB50, 0xFDFF, "Arab"),  # Arabic Presentation Forms
    (0xFE70, 0xFEFF, "Arab"),
)


class LidResult(Frozen):
    """What `/text-lid` said. Either field may be absent on a malformed reply."""

    language_code: str | None = None
    script_code: str | None = None


class Resolution(Frozen):
    """How the language question was settled, and on whose authority.

    `source` is carried all the way to the reader rather than kept internal: a
    reader who can see we guessed can correct us, and one who can see we asked
    knows we did not guess.
    """

    language: str | None
    source: LanguageSource
    script: str
    lid_language: str | None = None
    needs_user: bool = False
    probe_language: str = ""

    @property
    def needs_second_pass(self) -> bool:
        """Whether the page has to be digitised again to be read properly.

        Digitisation is the slow, paid step, so a probe that happened to guess
        right must not be repeated.
        """
        return bool(self.language) and self.language != self.probe_language


def _script_of(char: str) -> str | None:
    code = ord(char)
    for low, high, script in _SCRIPT_RANGES:
        if low <= code <= high:
            return script
    return None


def dominant_script(text: str) -> str:
    """The most frequent script in `text`, as a 4-letter ISO 15924 code.

    Only letters vote. Digits, punctuation and whitespace are shared across
    every one of these languages, so counting them would let a table of figures
    or a date decide what language a page is in. Combining marks are skipped
    for the same reason -- they follow a letter that has already voted.

    Returns UNDETERMINED when nothing countable remains.
    """
    counts: Counter[str] = Counter()
    for char in text:
        if not char.isalpha():
            continue
        script = _script_of(char)
        if script is not None:
            counts[script] += 1

    if not counts:
        return UNDETERMINED

    # most_common breaks ties by first insertion, i.e. by first appearance on
    # the page -- arbitrary, but stable, which is what a cached document needs.
    return counts.most_common(1)[0][0]


def _orthographic_language(script: str, text: str) -> str | None:
    """A language pinned by letters only it uses, or None when there is no such evidence.

    Assamese is the case that matters: it shares Bengali's script, and LID
    cannot name it at all, so an Assamese page would otherwise be read as
    Bengali by both the script map and LID agreeing with it -- a silent misread
    of exactly the kind the ambiguity rule exists to prevent. Two letters
    settle it deterministically, with no extra call.
    """
    if script == "Beng" and any(letter in text for letter in ASSAMESE_LETTERS):
        return "as-IN"
    return None


def sample_for_lid(doc: DigitisedDoc) -> str:
    """Text to send to LID: up to LID_MAX_CHARS from the document's longest block.

    The longest block, not the first. A bilingual government form opens with an
    English header, and sampling from the top would report en-IN for a page
    that is Tamil from the second line down.
    """
    body = max((b.text for b in doc.blocks), key=len, default="") or doc.text
    return body.strip()[:LID_MAX_CHARS]


def identify_language(text: str) -> LidResult:
    """Ask Sarvam's LID what this text is.

    Raises the same typed errors as a chat call, so callers can tell "your key
    is wrong" from "the service is down" -- and so a caller that wants to
    continue without detection can catch exactly one base class.
    """
    try:
        response = httpx.post(
            LID_URL,
            # The API 422s past its limit. Callers should sample first; failing
            # the whole call over one character would lose detection for nothing.
            json={"input": text[:LID_MAX_CHARS]},
            headers={
                "api-subscription-key": api_key(),
                "Content-Type": "application/json",
            },
            timeout=LID_TIMEOUT,
        )
    except httpx.RequestError as exc:
        raise ChatError(f"Cannot reach {LID_URL}: {exc}") from exc

    if response.status_code == 403:
        raise AuthError("Sarvam rejected the API key (403). Check SARVAM_API_KEY.")
    if response.status_code == 429:
        raise RateLimitError(f"Rate limited or out of quota (429): {response.text[:300]}")
    if response.status_code >= 400:
        raise ChatError(f"Language detection failed ({response.status_code}): {response.text[:500]}")

    try:
        payload = response.json()
    except ValueError as exc:
        raise ChatError("Sarvam returned a non-JSON response body.") from exc

    return LidResult(
        language_code=payload.get("language_code") or None,
        script_code=payload.get("script_code") or None,
    )


def resolve_language(doc: DigitisedDoc, *, probe_language: str) -> Resolution:
    """Decide what language `doc` is in, and record how we decided.

    Checked in this order, strongest evidence first:

    1. **Letters only one language uses** -- deterministic and ours, so it
       outranks LID (which cannot name Assamese in the first place).
    2. **An ambiguous script.** The script names nothing on its own, so LID is
       the only source that can tell Hindi from Marathi, and it is accepted
       *only* when it names a language actually written in the script we can
       see. Hindi is by far the likeliest upload and hi-IN/mr-IN are genuinely
       within LID's eleven, so refusing to use that would send every Hindi
       reader to a picker for nothing. `source=DETECTED` already tells them we
       inferred rather than asked, and the override stays available. Anything
       else -- a contradicting language, one outside LID's eleven, an empty
       reply, an outage -- falls through to the reader.
    3. **LID agreeing with a script that names one language** -- trust LID.
    4. **Otherwise the script**, which is the checkable one.

    A LID outage is never fatal: on a 1:1 script the script decides alone, and
    on an ambiguous one the reader is asked. Losing detection must not lose the
    document.
    """
    script = dominant_script(doc.text)

    try:
        lid = identify_language(sample_for_lid(doc))
    except ChatError:
        lid = LidResult()

    def resolved(language: str | None, source: LanguageSource) -> Resolution:
        return Resolution(
            language=language,
            source=source,
            script=script,
            lid_language=lid.language_code,
            needs_user=language is None,
            probe_language=probe_language,
        )

    pinned = _orthographic_language(script, doc.text)
    if pinned is not None:
        return resolved(pinned, LanguageSource.SCRIPT)

    if script in AMBIGUOUS_SCRIPTS:
        proposal = lid.language_code
        if proposal in SUPPORTED_LANGUAGES and proposal in SCRIPT_LANGUAGES.get(script, ()):
            return resolved(proposal, LanguageSource.DETECTED)
        # No guess of ours here. LID's proposal is still carried so the picker
        # can open on it, but it stays a suggestion to the reader.
        return resolved(None, LanguageSource.USER)

    if script not in SCRIPT_TO_LANGUAGE:
        return resolved(None, LanguageSource.USER)

    if lid.script_code == script and lid.language_code in SUPPORTED_LANGUAGES:
        return resolved(lid.language_code, LanguageSource.DETECTED)

    return resolved(SCRIPT_TO_LANGUAGE[script], LanguageSource.SCRIPT)
