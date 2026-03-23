"""Agent: search job listings via Perplexity Sonar deep research."""

from __future__ import annotations

from typing import Any

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

JSON_REPAIR_SYSTEM_PROMPT = """You are a strict JSON formatter.
Given raw model output, return ONLY valid JSON and nothing else."""


def _normalize_jobs(data: Any) -> list[dict[str, Any]]:
    """Normalize model output to a clean list of job dictionaries."""
    if isinstance(data, list):
        candidates = data
    elif isinstance(data, dict):
        jobs_value = data.get("jobs")
        if isinstance(jobs_value, list):
            candidates = jobs_value
        elif isinstance(jobs_value, dict):
            candidates = [jobs_value]
        else:
            candidates = [data]
    else:
        return []

    normalized: list[dict[str, Any]] = []
    for item in candidates:
        if not isinstance(item, dict):
            continue

        required_skills = item.get("required_skills", [])
        if isinstance(required_skills, str):
            required_skills = [s.strip() for s in required_skills.split(",") if s.strip()]
        elif not isinstance(required_skills, list):
            required_skills = []

        title = str(item.get("title", "")).strip()
        company = str(item.get("company", "")).strip()
        if not title or not company:
            continue

        normalized.append(
            {
                "title": title,
                "company": company,
                "location": str(item.get("location", "")).strip(),
                "description": str(item.get("description", "")).strip(),
                "required_skills": required_skills,
                "experience_level": str(item.get("experience_level", "")).strip(),
                "salary_range": str(item.get("salary_range", "")).strip(),
                "source_url": str(item.get("source_url", "")).strip(),
            }
        )

    return normalized


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
        # Retry once by asking the model to strictly reformat previous output as JSON.
        repair = call_perplexity(
            api_key,
            JSON_REPAIR_SYSTEM_PROMPT,
            "Convert the following content into a valid JSON array of job objects. "
            "Return ONLY JSON.\n\n"
            f"{result['content']}",
        )
        if "error" in repair:
            return {
                "error": "Failed to parse job results: AI returned invalid JSON and JSON repair failed."
            }
        parsed = parse_json_response(repair.get("content", ""))
        if parsed is None:
            return {"error": "Failed to parse job results: AI returned invalid JSON."}

    jobs = _normalize_jobs(parsed)
    if not jobs:
        return {"error": "AI job search returned no valid job entries."}

    return {"jobs": jobs, "citations": result.get("citations", [])}
