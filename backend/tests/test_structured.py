"""Structured-output resilience.

Both Sarvam models degenerate under `response_format` -- valid JSON prefix,
then whitespace until max_tokens, returned as HTTP 200. These tests pin the
fallback so a silent truncation can never reach the pipeline as if it were an
answer.
"""

import pytest

from askdoc import structured
from askdoc.sarvam_http import AuthError
from askdoc.structured import MalformedOutput, complete_structured

SCHEMA = {
    "name": "thing",
    "schema": {
        "type": "object",
        "properties": {"value": {"type": "string"}},
        "required": ["value"],
    },
}
MESSAGES = [{"role": "user", "content": "hi"}]


def schema_reply(content, finish_reason="stop"):
    return {"choices": [{"finish_reason": finish_reason, "message": {"content": content}}]}


def tool_reply(arguments):
    return {
        "choices": [
            {
                "finish_reason": "tool_calls",
                "message": {
                    "tool_calls": [{"function": {"name": "thing", "arguments": arguments}}]
                },
            }
        ]
    }


@pytest.fixture
def transport(monkeypatch):
    """Record each request and reply from a scripted queue."""
    calls: list[dict] = []

    def install(*replies):
        queue = list(replies)

        def fake_post(body, **_):
            calls.append(body)
            reply = queue.pop(0)
            if isinstance(reply, Exception):
                raise reply
            return reply

        monkeypatch.setattr(structured, "post_chat", fake_post)
        return calls

    return install


class TestPrimaryPath:
    def test_valid_schema_output_is_returned(self, transport):
        transport(schema_reply('{"value": "ok"}'))
        assert complete_structured(MESSAGES, SCHEMA) == {"value": "ok"}

    def test_primary_request_asks_for_the_schema(self, transport):
        calls = transport(schema_reply('{"value": "ok"}'))
        complete_structured(MESSAGES, SCHEMA)
        assert calls[0]["response_format"]["json_schema"] is SCHEMA

    def test_reasoning_is_disabled(self, transport):
        # Reasoning tokens can consume the whole budget and return nothing.
        calls = transport(schema_reply('{"value": "ok"}'))
        complete_structured(MESSAGES, SCHEMA)
        assert calls[0]["reasoning_effort"] is None


class TestDegenerationFallback:
    def test_truncated_output_falls_back_to_a_tool_call(self, transport):
        # The exact observed failure: a valid prefix, padded to max_tokens.
        calls = transport(
            schema_reply('{\n"value"\n   \n   \n', finish_reason="length"),
            tool_reply('{"value": "rescued"}'),
        )
        assert complete_structured(MESSAGES, SCHEMA) == {"value": "rescued"}
        assert calls[1]["tool_choice"] == "required"

    def test_empty_content_falls_back(self, transport):
        transport(schema_reply(None), tool_reply('{"value": "rescued"}'))
        assert complete_structured(MESSAGES, SCHEMA) == {"value": "rescued"}

    def test_invalid_json_falls_back(self, transport):
        transport(schema_reply("{not json"), tool_reply('{"value": "rescued"}'))
        assert complete_structured(MESSAGES, SCHEMA) == {"value": "rescued"}

    def test_failure_in_both_strategies_raises(self, transport):
        transport(schema_reply(None), tool_reply("{still not json"))
        with pytest.raises(MalformedOutput):
            complete_structured(MESSAGES, SCHEMA)

    def test_missing_tool_call_raises(self, transport):
        transport(schema_reply(None), {"choices": [{"message": {}}]})
        with pytest.raises(MalformedOutput):
            complete_structured(MESSAGES, SCHEMA)


class TestNonRetryableErrors:
    def test_auth_failure_is_not_retried(self, transport):
        # The fallback would fail identically; retrying just wastes demo time.
        calls = transport(AuthError("bad key"))
        with pytest.raises(AuthError):
            complete_structured(MESSAGES, SCHEMA)
        assert len(calls) == 1


class TestDecoding:
    def test_a_json_array_is_rejected(self, transport):
        transport(schema_reply("[1, 2, 3]"), tool_reply("[1, 2, 3]"))
        with pytest.raises(MalformedOutput):
            complete_structured(MESSAGES, SCHEMA)
