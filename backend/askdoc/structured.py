"""Get structured JSON out of a Sarvam model, reliably.

Both available models degenerate under `response_format`: they emit a valid
JSON prefix and then pad with whitespace until `max_tokens`, returning HTTP 200
with unusable content. Measured on sarvam-30b (20 of 21 calls) and observed on
sarvam-105b too, where it stalls at the point of committing to a negative
verdict.

Forced tool calls do not have this failure mode, so every structured request
tries the schema first and falls back to a tool call. Callers get a dict or an
exception -- never silently truncated JSON.
"""

from __future__ import annotations

import json
from typing import Any

from .config import (
    QA_FALLBACK_MODEL,
    QA_MAX_TOKENS,
    QA_MODEL,
    QA_REASONING_EFFORT,
    QA_SEED,
    QA_TEMPERATURE,
)
from .sarvam_http import ChatError, post_chat


class MalformedOutput(ChatError):
    """The model replied, but not with usable structured output."""


def _body(messages: list[dict], model: str) -> dict[str, Any]:
    return {
        "model": model,
        "messages": messages,
        "temperature": QA_TEMPERATURE,
        "max_tokens": QA_MAX_TOKENS,
        "reasoning_effort": QA_REASONING_EFFORT,
        "seed": QA_SEED,
    }


def _decode(payload: str, *, source: str) -> dict:
    try:
        data = json.loads(payload)
    except json.JSONDecodeError as exc:
        raise MalformedOutput(f"{source} returned invalid JSON: {payload[:160]!r}") from exc
    if not isinstance(data, dict):
        raise MalformedOutput(f"{source} returned {type(data).__name__}, expected object")
    return data


def _via_schema(messages: list[dict], schema: dict, model: str) -> dict:
    body = _body(messages, model)
    body["response_format"] = {"type": "json_schema", "json_schema": schema}

    choice = post_chat(body)["choices"][0]

    if choice.get("finish_reason") == "length":
        # The degeneration mode. Fail loudly so the tool strategy runs.
        raise MalformedOutput(f"{model} hit max_tokens before closing the object.")

    content = choice["message"].get("content")
    if not content:
        raise MalformedOutput(f"{model} returned empty content.")

    return _decode(content, source=model)


def _via_tool(messages: list[dict], schema: dict, model: str) -> dict:
    body = _body(messages, model)
    body["tool_choice"] = "required"
    body["tools"] = [
        {
            "type": "function",
            "function": {
                "name": schema["name"],
                "description": schema.get("description", "Record the structured result."),
                "parameters": schema["schema"],
            },
        }
    ]

    tool_calls = post_chat(body)["choices"][0]["message"].get("tool_calls")
    if not tool_calls:
        raise MalformedOutput(f"{model} did not call {schema['name']}.")

    return _decode(tool_calls[0]["function"]["arguments"], source=f"{model}/tool")


def complete_structured(
    messages: list[dict],
    schema: dict,
    *,
    model: str = QA_MODEL,
    fallback_model: str = QA_FALLBACK_MODEL,
) -> dict:
    """Return the model's structured output as a dict.

    Auth and quota errors propagate immediately -- the fallback would fail the
    same way, and retrying a bad key just wastes the demo's time.
    """
    try:
        return _via_schema(messages, schema, model)
    except MalformedOutput:
        return _via_tool(messages, schema, fallback_model)
