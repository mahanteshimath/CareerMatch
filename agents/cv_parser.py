"""Agent: extract structured data from CV text using Perplexity Sonar."""

from __future__ import annotations

from utils.perplexity_client import call_perplexity, parse_json_response

CV_PARSER_SYSTEM_PROMPT = """You are an expert CV/resume parser. Given the raw text of a CV,
extract structured information and return ONLY valid JSON with these keys:

{
    "name": "Full name",
    "email": "Email address",
    "phone": "Phone number",
    "summary": "Professional summary (2-3 sentences)",
    "education": [
        {
            "degree": "Degree name",
            "field": "Field of study",
            "institution": "University/College",
            "year": "Graduation year or expected",
            "gpa": "GPA if mentioned"
        }
    ],
    "experience": [
        {
            "title": "Job title",
            "company": "Company name",
            "duration": "Start - End",
            "description": "Key responsibilities and achievements"
        }
    ],
    "skills": ["skill1", "skill2"],
    "publications": ["publication1"],
    "certifications": ["cert1"],
    "languages": ["language1"],
    "research_interests": ["interest1"]
}

If a field is not found in the CV, use null or an empty list.
Return ONLY the JSON, no markdown formatting or explanation."""


def parse_cv(api_key: str, cv_text: str) -> dict:
    """Parse CV text into structured JSON using Perplexity Sonar.

    Returns:
        Parsed CV dict on success, or {"error": str} on failure.
    """
    result = call_perplexity(
        api_key,
        CV_PARSER_SYSTEM_PROMPT,
        f"Parse the following CV:\n\n{cv_text[:15000]}",
    )
    if "error" in result:
        return result

    parsed = parse_json_response(result["content"])
    if parsed is None:
        return {"error": "Failed to parse CV: AI returned invalid JSON."}
    return parsed
