"""Agent: search university positions via Perplexity Sonar deep research."""

from __future__ import annotations

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
        return {"error": "Failed to parse position results: AI returned invalid JSON."}

    positions = parsed if isinstance(parsed, list) else parsed.get("positions", [parsed])
    return {"positions": positions, "citations": result.get("citations", [])}
