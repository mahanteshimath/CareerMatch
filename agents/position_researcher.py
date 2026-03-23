"""Agent: search university positions via Perplexity Sonar deep research."""

from __future__ import annotations

from typing import Any

from utils.perplexity_client import call_perplexity, parse_json_response

POSITION_RESEARCHER_SYSTEM_PROMPT = """You are a university position research specialist.
Given a candidate's profile and search criteria, find REAL, CURRENT university positions
(Masters, PhD, or Postdoc) that match their background.

Search for positions that:
1. Match the requested position type (Masters/PhD/Postdoc)
2. Are in the specified continent/region
3. Have application deadlines that are still open (current date context provided)
4. Align with the candidate's research interests, skills, and education

Return ONLY valid JSON — an array of position objects:
[
    {
        "title": "Position title",
        "university": "University name",
        "country": "Country",
        "continent": "Continent",
        "position_type": "Masters/PhD/Postdoc",
        "deadline": "YYYY-MM-DD or 'Open until filled'",
        "description": "Position description (2-3 sentences)",
        "requirements": "Key requirements",
        "professor_name": "Supervisor name if available",
        "professor_email": "Contact email if available",
        "source_url": "URL to the position listing"
    }
]

Find at least 5-10 positions. Only include positions you are confident are real.
Return ONLY the JSON array, no markdown or explanation."""

JSON_REPAIR_SYSTEM_PROMPT = """You are a strict JSON formatter.
Given raw model output, return ONLY valid JSON and nothing else."""

POSITION_RESEARCHER_RELAXED_SYSTEM_PROMPT = """You are a university position researcher.
Return ONLY valid JSON as an array of position objects. Use this schema:
[
  {
    "title": "Position title",
    "university": "University name or 'Unknown'",
    "country": "Country or empty string",
    "continent": "Continent or empty string",
    "position_type": "Masters/PhD/Postdoc/Unknown",
    "deadline": "YYYY-MM-DD or text",
    "description": "Short summary",
    "requirements": "Key requirements",
    "professor_name": "Name or empty string",
    "professor_email": "Email or empty string",
    "source_url": "Listing URL if available"
  }
]
If unknown, use empty string and keep title populated.
Return ONLY JSON."""


def _pick_first(item: dict[str, Any], keys: list[str]) -> str:
    """Get first non-empty string value from possible alternate keys."""
    for key in keys:
        value = item.get(key)
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return ""


def _normalize_positions(data: Any) -> list[dict[str, Any]]:
    """Normalize model output to a clean list of position dictionaries."""
    if isinstance(data, list):
        candidates = data
    elif isinstance(data, dict):
        positions_value = data.get("positions")
        if isinstance(positions_value, list):
            candidates = positions_value
        elif isinstance(positions_value, dict):
            candidates = [positions_value]
        else:
            candidates = [data]
    else:
        return []

    normalized: list[dict[str, Any]] = []
    for item in candidates:
        if not isinstance(item, dict):
            continue

        title = _pick_first(item, ["title", "position", "role", "position_title"])
        university = _pick_first(item, ["university", "institution", "organization"]) or "Unknown"
        if not title:
            continue

        normalized.append(
            {
                "title": title,
                "university": university,
                "country": _pick_first(item, ["country", "nation"]),
                "continent": _pick_first(item, ["continent", "region"]),
                "position_type": _pick_first(item, ["position_type", "type", "program_type"]),
                "deadline": _pick_first(item, ["deadline", "application_deadline"]),
                "description": _pick_first(item, ["description", "summary"]),
                "requirements": _pick_first(item, ["requirements", "eligibility"]),
                "professor_name": _pick_first(item, ["professor_name", "supervisor", "advisor"]),
                "professor_email": _pick_first(item, ["professor_email", "contact_email", "email"]),
                "source_url": _pick_first(item, ["source_url", "url", "link", "apply_url"]),
            }
        )

    return normalized


def _positions_from_citations(citations: list[str]) -> list[dict[str, Any]]:
    """Build minimal position cards from citation URLs as last-resort fallback."""
    positions: list[dict[str, Any]] = []
    for idx, url in enumerate(citations, 1):
        if not isinstance(url, str) or not url.strip():
            continue
        positions.append(
            {
                "title": f"Position Source {idx}",
                "university": "Unknown",
                "country": "",
                "continent": "",
                "position_type": "",
                "deadline": "",
                "description": "Open the source link to view full position details.",
                "requirements": "",
                "professor_name": "",
                "professor_email": "",
                "source_url": url.strip(),
            }
        )
    return positions


def search_positions(
    api_key: str,
    cv_summary: str,
    position_type: str,
    continent: str,
    current_date: str,
) -> dict:
    """Search for university positions matching the candidate's profile.

    Returns:
        {"positions": [...], "citations": [...]} on success, or {"error": str} on failure.
    """
    user_prompt = (
        f"Today's date: {current_date}\n\n"
        f"Candidate Profile:\n{cv_summary}\n\n"
        f"Search Criteria:\n"
        f"- Position Type: {position_type}\n"
        f"- Region: {continent}\n"
        f"- Only positions with open application deadlines\n\n"
        f"Find matching university positions."
    )
    result = call_perplexity(
        api_key,
        POSITION_RESEARCHER_SYSTEM_PROMPT,
        user_prompt,
        web_search_options={"search_context_size": "high"},
    )
    if "error" in result:
        return result

    parsed = parse_json_response(result["content"])
    if parsed is None:
        # Retry once by asking the model to strictly reformat previous output as JSON.
        repair = call_perplexity(
            api_key,
            JSON_REPAIR_SYSTEM_PROMPT,
            "Convert the following content into a valid JSON array of position objects. "
            "Return ONLY JSON.\n\n"
            f"{result['content']}",
        )
        if "error" in repair:
            return {
                "error": "Failed to parse position results: AI returned invalid JSON and JSON repair failed."
            }
        parsed = parse_json_response(repair.get("content", ""))
        if parsed is None:
            return {"error": "Failed to parse position results: AI returned invalid JSON."}

    positions = _normalize_positions(parsed)
    if not positions:
        # Retry with a relaxed prompt that tolerates unknown fields.
        retry = call_perplexity(
            api_key,
            POSITION_RESEARCHER_RELAXED_SYSTEM_PROMPT,
            user_prompt,
            web_search_options={"search_context_size": "high"},
        )
        if "error" not in retry:
            retry_parsed = parse_json_response(retry.get("content", ""))
            positions = _normalize_positions(retry_parsed)
            if positions:
                return {
                    "positions": positions,
                    "citations": retry.get("citations", result.get("citations", [])),
                }

        # Last resort: show clickable sources instead of hard-failing UX.
        fallback_positions = _positions_from_citations(result.get("citations", []))
        if fallback_positions:
            return {"positions": fallback_positions, "citations": result.get("citations", [])}

        return {"error": "AI position search returned no valid position entries."}

    return {"positions": positions, "citations": result.get("citations", [])}
