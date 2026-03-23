"""Agent: search job listings via Perplexity Sonar deep research."""

from __future__ import annotations

from utils.perplexity_client import call_perplexity, parse_json_response

JOB_RESEARCHER_SYSTEM_PROMPT = """You are a job market research specialist.
Given a candidate's profile (skills, education, experience), find REAL, CURRENT
job listings that match their qualifications.

Return ONLY valid JSON — an array of job objects:
[
    {
        "title": "Job title",
        "company": "Company name",
        "location": "City, Country",
        "description": "Job description (2-3 sentences)",
        "required_skills": ["skill1", "skill2"],
        "experience_level": "Entry/Mid/Senior",
        "salary_range": "If available, otherwise null",
        "source_url": "URL to the job listing"
    }
]

Find at least 5-10 relevant positions. Prioritise roles that closely match
the candidate's existing skills and experience level.
Return ONLY the JSON array, no markdown or explanation."""


def search_jobs(api_key: str, cv_summary: str) -> dict:
    """Search for job listings matching the candidate's profile.

    Returns:
        {"jobs": [...], "citations": [...]} on success, or {"error": str} on failure.
    """
    result = call_perplexity(
        api_key,
        JOB_RESEARCHER_SYSTEM_PROMPT,
        f"Candidate Profile:\n{cv_summary}\n\nFind matching job listings that are currently open.",
        web_search_options={"search_context_size": "high"},
    )
    if "error" in result:
        return result

    parsed = parse_json_response(result["content"])
    if parsed is None:
        return {"error": "Failed to parse job results: AI returned invalid JSON."}

    jobs = parsed if isinstance(parsed, list) else parsed.get("jobs", [parsed])
    return {"jobs": jobs, "citations": result.get("citations", [])}
