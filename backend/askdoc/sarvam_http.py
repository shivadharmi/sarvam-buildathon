"""REST transport for Sarvam chat completions.

Why not the SDK: `sarvamai` 0.1.28 exposes `tools`/`tool_choice` but not
`response_format`, and we need both -- one per strategy in `qa.py`. Going
direct keeps the two strategies symmetrical instead of split across two
client styles.

Why httpx rather than urllib: the python.org macOS build does not trust the
system keychain, so urllib fails with CERTIFICATE_VERIFY_FAILED. httpx bundles
certifi, which is also why the SDK's own calls work.

Digitisation still uses the SDK, which genuinely earns its keep there by
collapsing a multi-step async job.
"""

from __future__ import annotations

from typing import Any

import httpx

from .config import api_key

CHAT_URL = "https://api.sarvam.ai/v1/chat/completions"
DEFAULT_TIMEOUT = 90.0


class ChatError(RuntimeError):
    """A chat call that cannot be retried into success."""


class AuthError(ChatError):
    """Bad or missing API key. Sarvam returns 403, not 401."""


class RateLimitError(ChatError):
    """429 -- rate limit or exhausted quota."""


def post_chat(body: dict[str, Any], *, timeout: float = DEFAULT_TIMEOUT) -> dict[str, Any]:
    """POST a chat completion and return the decoded response.

    Raises a typed ChatError rather than leaking transport exceptions, so
    callers can distinguish "your key is wrong" from "try the other strategy".
    """
    try:
        response = httpx.post(
            CHAT_URL,
            json=body,
            headers={
                "api-subscription-key": api_key(),
                "Content-Type": "application/json",
            },
            timeout=timeout,
        )
    except httpx.RequestError as exc:
        raise ChatError(f"Cannot reach {CHAT_URL}: {exc}") from exc

    if response.status_code == 403:
        raise AuthError("Sarvam rejected the API key (403). Check SARVAM_API_KEY.")
    if response.status_code == 429:
        raise RateLimitError(f"Rate limited or out of quota (429): {response.text[:300]}")
    if response.status_code >= 400:
        raise ChatError(f"Chat request failed ({response.status_code}): {response.text[:500]}")

    try:
        return response.json()
    except ValueError as exc:
        raise ChatError("Sarvam returned a non-JSON response body.") from exc
