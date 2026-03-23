"""Shared Perplexity API client with response-shape normalization."""

from __future__ import annotations

import json
import logging
import random
import time
from typing import Any

import requests

from config.settings import PERPLEXITY_API_URL, PERPLEXITY_MODEL


logger = logging.getLogger(__name__)

_RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}


def call_perplexity(
    api_key: str,
    system_prompt: str,
    user_prompt: str,
    *,
    model: str = PERPLEXITY_MODEL,
    temperature: float = 0.0,
    web_search_options: dict[str, Any] | None = None,
    timeout: int = 90,
    max_retries: int = 2,
) -> dict[str, Any]:
    """Call the Perplexity API.

    Args:
        api_key: Perplexity API key.
        system_prompt: System-level instruction.
        user_prompt: User message / query.
        model: Perplexity model name (default: sonar).
        temperature: Sampling temperature.
        web_search_options: Optional web search configuration.
        timeout: Request timeout in seconds.
        max_retries: Number of retries after initial attempt for transient failures.

    Returns:
        On success: {"content": str, "citations": list[str]}
        On failure: {"error": str}
    """
    payload: dict[str, Any] = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": temperature,
    }
    if web_search_options:
        payload["web_search_options"] = web_search_options

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    total_attempts = max(1, max_retries + 1)
    last_error = ""

    for attempt in range(1, total_attempts + 1):
        try:
            response = requests.post(
                PERPLEXITY_API_URL,
                json=payload,
                headers=headers,
                timeout=timeout,
            )

            if response.status_code in _RETRYABLE_STATUS_CODES:
                last_error = f"HTTP {response.status_code}: {response.text[:300]}"
                should_retry = attempt < total_attempts
                if should_retry:
                    _sleep_before_retry(attempt)
                    continue

                logger.warning(
                    "perplexity_retryable_status_exhausted",
                    extra={"status_code": response.status_code, "attempts": attempt},
                )
                return {"error": f"Perplexity temporary failure after retries ({last_error})"}

            response.raise_for_status()
            result = response.json()
            normalized = _normalize_perplexity_response(result)
            if normalized is not None:
                return normalized

            return {"error": f"Unexpected API response: {json.dumps(result)[:500]}"}

        except requests.Timeout:
            last_error = "Request timed out."
            if attempt < total_attempts:
                _sleep_before_retry(attempt)
                continue
            return {
                "error": "Request timed out after retries. Perplexity API took too long to respond."
            }
        except requests.HTTPError as e:
            status = e.response.status_code if e.response is not None else "unknown"
            body = e.response.text[:300] if e.response is not None else ""
            return {"error": f"API error (HTTP {status}): {body}"}
        except requests.RequestException as e:
            last_error = f"Connection error: {e}"
            if attempt < total_attempts:
                _sleep_before_retry(attempt)
                continue
            return {"error": f"Connection error after retries: {e}"}
        except json.JSONDecodeError as e:
            return {"error": f"Failed to parse API response: {e}"}

    return {"error": f"Perplexity request failed: {last_error}"}


def _sleep_before_retry(attempt: int) -> None:
    """Backoff with bounded jitter for transient API failures."""
    delay_seconds = min(8.0, (2 ** (attempt - 1)) + random.uniform(0.0, 0.3))
    time.sleep(delay_seconds)


def _normalize_perplexity_response(result: dict[str, Any]) -> dict[str, Any] | None:
    """Normalize different Perplexity response shapes into a stable output schema."""
    content = _extract_content(result)
    if not content:
        return None

    citations = _extract_citations(result)
    return {"content": content, "citations": citations}


def _extract_content(result: dict[str, Any]) -> str:
    """Extract model text from known response layouts."""
    # Classic chat completions shape.
    choices = result.get("choices")
    if isinstance(choices, list) and choices:
        message = choices[0].get("message", {}) if isinstance(choices[0], dict) else {}
        content = message.get("content") if isinstance(message, dict) else ""

        if isinstance(content, str):
            return content
        if isinstance(content, list):
            parts: list[str] = []
            for block in content:
                if isinstance(block, dict):
                    text = block.get("text") or block.get("content")
                    if isinstance(text, str) and text:
                        parts.append(text)
            if parts:
                return "\n".join(parts)

    # Agent-like / tool style shapes.
    output_text = result.get("output_text")
    if isinstance(output_text, str) and output_text:
        return output_text

    answer = result.get("answer")
    if isinstance(answer, str) and answer:
        return answer

    content = result.get("content")
    if isinstance(content, str) and content:
        return content

    return ""


def _extract_citations(result: dict[str, Any]) -> list[str]:
    """Extract URLs from known citation/source fields."""
    citations = result.get("citations", [])
    if isinstance(citations, list):
        normalized = [str(item) for item in citations if item]
        if normalized:
            return normalized

    sources = result.get("sources")
    if isinstance(sources, list):
        urls: list[str] = []
        for item in sources:
            if isinstance(item, str):
                urls.append(item)
            elif isinstance(item, dict):
                candidate = item.get("url") or item.get("source")
                if candidate:
                    urls.append(str(candidate))
        return urls

    return []


def parse_json_response(raw_content: str) -> dict | list | None:
    """Strip markdown fences and parse JSON from an LLM response.

    Returns parsed JSON or None if parsing fails.
    """
    content = raw_content.strip()

    # Strip ```json or ``` fences.
    if content.startswith("```"):
        first_nl = content.find("\n")
        content = content[first_nl + 1:] if first_nl != -1 else content[3:]
    if content.endswith("```"):
        content = content[:-3]
    content = content.strip()

    # Fast path: content is already pure JSON.
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        pass

    # Fallback: extract the first balanced JSON object/array from mixed text.
    extracted = _extract_balanced_json(content)
    if extracted is None:
        return None

    try:
        return json.loads(extracted)
    except json.JSONDecodeError:
        return None


def _extract_balanced_json(text: str) -> str | None:
    """Extract first balanced JSON object/array from free-form text."""
    start = -1
    opener = ""
    for i, ch in enumerate(text):
        if ch in "[{":
            start = i
            opener = ch
            break

    if start == -1:
        return None

    closer = "]" if opener == "[" else "}"
    depth = 0
    in_string = False
    escape = False

    for i in range(start, len(text)):
        ch = text[i]

        if escape:
            escape = False
            continue

        if ch == "\\":
            escape = True
            continue

        if ch == '"':
            in_string = not in_string
            continue

        if in_string:
            continue

        if ch in "[{":
            depth += 1
        elif ch in "]}":
            depth -= 1
            if depth == 0 and ch == closer:
                return text[start : i + 1]

    return None
