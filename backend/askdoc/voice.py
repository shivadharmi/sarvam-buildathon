"""Speech in and speech out.

Two capabilities, and they sit on opposite sides of the trust boundary:

* **Speech-to-text is input.** A transcript is exactly the same class of thing
  as a typed question -- reader-authored, never a citation. It cannot weaken
  the core invariant, because nothing it produces is ever quoted back as the
  document's words.

  Its hazard is different and easy to miss: a *misheard* question produces a
  perfectly verified citation answering something the reader never asked. Every
  trust signal on screen would say "verified", and it would be true, and the
  answer would still be to the wrong question. That is why `transcribe` returns
  the text and nothing else -- the caller shows it to the reader and waits.
  Nothing here submits a question.

* **Text-to-speech is output**, and one of the two things it reads aloud is the
  citation. Audio strips the visual distinction between the document's words
  and the model's, so the *caller* must never be able to decide what the
  document said: `speak_quote` takes offsets and re-slices from our own cached
  text. Only `speak_answer` accepts a string, and an answer was always
  model-authored prose.

Both go over httpx for the same reason chat does -- the python.org macOS build
does not trust the system keychain, so urllib fails CERTIFICATE_VERIFY_FAILED.
"""

from __future__ import annotations

import httpx

from .config import (
    MAX_SPEAK_CHARS,
    STT_MODEL,
    STT_MODE,
    TTS_CHUNK_CHARS,
    TTS_MODEL,
    TTS_SAMPLE_RATE,
    TTS_SPEAKER,
    api_key,
)
from .sarvam_http import AuthError, ChatError, RateLimitError

STT_URL = "https://api.sarvam.ai/speech-to-text"
TTS_URL = "https://api.sarvam.ai/text-to-speech"

# Generous: a spoken question is a few seconds of opus. The sync endpoint caps
# at 30s of audio anyway, so this is a guard against a mistaken upload rather
# than a real ceiling.
MAX_AUDIO_BYTES = 8 * 1024 * 1024

DEFAULT_TIMEOUT = 60.0


class VoiceError(ChatError):
    """A speech call that cannot be retried into success.

    Subclasses ChatError so the API layer's existing 502/429 mapping covers
    voice without a second set of handlers -- and so a voice outage is reported
    as an outage, never as the document being silent.
    """


def _raise_for_status(response: httpx.Response, what: str) -> None:
    """Translate Sarvam's status codes into the errors callers already handle."""
    if response.status_code == 403:
        raise AuthError("Sarvam rejected the API key (403). Check SARVAM_API_KEY.")
    if response.status_code == 429:
        raise RateLimitError(f"Rate limited or out of quota (429): {response.text[:300]}")
    if response.status_code >= 400:
        raise VoiceError(f"{what} failed ({response.status_code}): {response.text[:500]}")


def transcribe(audio: bytes, *, filename: str, language: str) -> str:
    """Turn recorded audio into text. The text is input, never a citation.

    `language` is the document's own language rather than "unknown": we already
    know what page the reader is looking at, and telling the recogniser beats
    making it guess.

    Saaras accepts webm and opus directly, which is what `MediaRecorder` emits
    in every browser we care about -- so nothing is transcoded on the way in.
    """
    if not audio:
        raise VoiceError("The recording was empty. Hold the button while speaking.")
    if len(audio) > MAX_AUDIO_BYTES:
        raise VoiceError("That recording is too long. Ask in a sentence or two.")

    try:
        response = httpx.post(
            STT_URL,
            headers={"api-subscription-key": api_key()},
            files={"file": (filename, audio, "application/octet-stream")},
            data={"model": STT_MODEL, "mode": STT_MODE, "language_code": language},
            timeout=DEFAULT_TIMEOUT,
        )
    except httpx.RequestError as exc:
        raise VoiceError(f"Cannot reach the speech service: {exc}") from exc

    _raise_for_status(response, "Transcription")

    try:
        payload = response.json()
    except ValueError as exc:
        raise VoiceError("The speech service returned an unreadable response.") from exc

    transcript = str(payload.get("transcript") or "").strip()
    if not transcript:
        # Silence is a real outcome, not a crash. Say so in the reader's terms.
        raise VoiceError("I couldn't make out any speech in that recording.")
    return transcript


def _chunks(text: str, size: int = TTS_CHUNK_CHARS) -> list[str]:
    """Split text into synthesis-sized pieces, preferring line boundaries.

    Returned as separate clips rather than being stitched into one WAV: joining
    encoded audio server-side means rewriting RIFF headers, and the browser can
    simply play a list in order.
    """
    pieces: list[str] = []
    remaining = text.strip()

    while len(remaining) > size:
        window = remaining[:size]
        # Break where the text already breaks, so a clip does not end mid-word.
        cut = max(window.rfind("\n"), window.rfind(". "), window.rfind(" "))
        if cut <= 0:
            cut = size
        pieces.append(remaining[:cut].strip())
        remaining = remaining[cut:].strip()

    if remaining:
        pieces.append(remaining)
    return pieces


def synthesise(text: str, *, language: str) -> tuple[list[str], bool]:
    """Read `text` aloud. Returns (base64 WAV clips in order, was_truncated).

    Callers must have established what `text` is. The `/speak` quote path
    re-slices it from the cached document; nothing here can tell the
    difference, which is exactly why that check belongs upstream.

    Truncation is returned rather than hidden. Audio that simply stops is
    indistinguishable from a page that simply ends, and letting the reader
    believe they have heard the whole citation when they have not is the same
    dishonesty as reporting our own limit as the document's silence.
    """
    body = text.strip()
    if not body:
        raise VoiceError("There is nothing to read aloud.")

    truncated = len(body) > MAX_SPEAK_CHARS
    if truncated:
        body = body[:MAX_SPEAK_CHARS]

    try:
        response = httpx.post(
            TTS_URL,
            headers={
                "api-subscription-key": api_key(),
                "Content-Type": "application/json",
            },
            json={
                "inputs": _chunks(body),
                "target_language_code": language,
                "speaker": TTS_SPEAKER,
                "model": TTS_MODEL,
                "speech_sample_rate": TTS_SAMPLE_RATE,
                # Normalises numbers and dates, which a page like this is full
                # of: "2,08,000" should be spoken, not spelled.
                "enable_preprocessing": True,
            },
            timeout=DEFAULT_TIMEOUT,
        )
    except httpx.RequestError as exc:
        raise VoiceError(f"Cannot reach the speech service: {exc}") from exc

    _raise_for_status(response, "Speech synthesis")

    try:
        payload = response.json()
    except ValueError as exc:
        raise VoiceError("The speech service returned an unreadable response.") from exc

    audios = [clip for clip in (payload.get("audios") or []) if isinstance(clip, str)]
    if not audios:
        raise VoiceError("The speech service returned no audio.")
    return audios, truncated
