from __future__ import annotations

from types import SimpleNamespace

from utils.perplexity_client import (
    call_perplexity,
    parse_json_response,
)


class _FakeResponse:
    def __init__(self, status_code: int, payload: dict | None = None, text: str = ""):
        self.status_code = status_code
        self._payload = payload or {}
        self.text = text

    def raise_for_status(self) -> None:
        if self.status_code >= 400 and self.status_code not in (429, 500, 502, 503, 504):
            raise Exception("http error")

    def json(self) -> dict:
        return self._payload


def test_parse_json_response_with_code_fence() -> None:
    raw = "```json\n{\"a\": 1, \"b\": [2, 3]}\n```"
    parsed = parse_json_response(raw)
    assert isinstance(parsed, dict)
    assert parsed["a"] == 1
    assert parsed["b"] == [2, 3]


def test_parse_json_response_with_wrapped_text() -> None:
    raw = "Result below:\n{\"k\": \"v\"}\nThanks"
    parsed = parse_json_response(raw)
    assert parsed == {"k": "v"}


def test_call_perplexity_returns_content(monkeypatch) -> None:
    def _fake_post(*args, **kwargs):
        return _FakeResponse(
            200,
            payload={
                "choices": [{"message": {"content": "ok"}}],
                "citations": ["https://example.com"],
            },
        )

    monkeypatch.setattr("requests.post", _fake_post)
    result = call_perplexity("key", "sys", "user", timeout=1, max_retries=0)
    assert result["content"] == "ok"
    assert result["citations"] == ["https://example.com"]


def test_call_perplexity_retries_retryable_status(monkeypatch) -> None:
    calls = {"count": 0}

    def _fake_post(*args, **kwargs):
        calls["count"] += 1
        if calls["count"] == 1:
            return _FakeResponse(429, text="rate limited")
        return _FakeResponse(
            200,
            payload={
                "choices": [{"message": {"content": "after-retry"}}],
                "citations": [],
            },
        )

    monkeypatch.setattr("requests.post", _fake_post)
    monkeypatch.setattr("utils.perplexity_client._sleep_before_retry", lambda attempt: None)

    result = call_perplexity("key", "sys", "user", timeout=1, max_retries=1)
    assert result["content"] == "after-retry"
    assert calls["count"] == 2


def test_call_perplexity_normalizes_output_text_shape(monkeypatch) -> None:
    def _fake_post(*args, **kwargs):
        return _FakeResponse(
            200,
            payload={
                "output_text": "agent-output",
                "sources": [{"url": "https://example.org/doc"}],
            },
        )

    monkeypatch.setattr("requests.post", _fake_post)
    result = call_perplexity("key", "sys", "user", timeout=1, max_retries=0)
    assert result["content"] == "agent-output"
    assert result["citations"] == ["https://example.org/doc"]
