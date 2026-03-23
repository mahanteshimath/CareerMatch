"""Shared Perplexity Sonar API client using requests (bypasses httpx/openai SSL issues)."""

from __future__ import annotations

import json
from typing import Any

import requests

from config.settings import PERPLEXITY_API_URL, PERPLEXITY_MODEL


def call_perplexity(
    api_key: str,
    system_prompt: str,
    user_prompt: str,
    *,
    model: str = PERPLEXITY_MODEL,
    temperature: float = 0.0,
    web_search_options: dict[str, Any] | None = None,
    timeout: int = 90,
) -> dict[str, Any]:
    """Call the Perplexity chat completions API.

    Args:
        api_key: Perplexity API key.
        system_prompt: System-level instruction.
        user_prompt: User message / query.
        model: Perplexity model name (default: sonar).
        temperature: Sampling temperature.
        web_search_options: Optional web search configuration.
        timeout: Request timeout in seconds.

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

    try:
        response = requests.post(
            PERPLEXITY_API_URL,
            json=payload,
            headers=headers,
            timeout=timeout,
        )
        response.raise_for_status()
        result = response.json()

        if "choices" in result and len(result["choices"]) > 0:
            message = result["choices"][0]["message"]
            content = message.get("content", "")
            citations = result.get("citations", [])
            return {"content": content, "citations": citations}

        return {"error": f"Unexpected API response: {json.dumps(result)[:500]}"}

    except requests.Timeout:
        return {"error": "Request timed out. Perplexity API took too long to respond."}
    except requests.HTTPError as e:
        status = e.response.status_code if e.response is not None else "unknown"
        body = ""
        if e.response is not None:
            body = e.response.text[:300]
        return {"error": f"API error (HTTP {status}): {body}"}
    except requests.RequestException as e:
        return {"error": f"Connection error: {e}"}
    except json.JSONDecodeError as e:
        return {"error": f"Failed to parse API response: {e}"}


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
