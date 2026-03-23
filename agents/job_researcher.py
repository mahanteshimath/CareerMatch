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

JOB_RESEARCHER_RELAXED_SYSTEM_PROMPT = """You are a job market research specialist.
Return ONLY valid JSON as an array of job objects. Use this schema:
[
    {
        "title": "Job title",
        "company": "Company name or 'Unknown'",
        "location": "Location or empty string",
        "description": "Short summary",
        "required_skills": ["skill1", "skill2"],
        "experience_level": "Entry/Mid/Senior/Unknown",
        "salary_range": "If available else empty string",
        "source_url": "Job URL if available"
    }
]

If some fields are unknown, keep them as empty strings and keep title populated.
Return ONLY JSON."""


def _pick_first(item: dict[str, Any], keys: list[str]) -> str:
        """Get first non-empty string value from a list of possible keys."""
        for key in keys:
                value = item.get(key)
                if value is None:
                        continue
                text = str(value).strip()
                if text:
                        return text
        return ""


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

        required_skills = item.get("required_skills", item.get("skills", []))
        if isinstance(required_skills, str):
            required_skills = [s.strip() for s in required_skills.split(",") if s.strip()]
        elif not isinstance(required_skills, list):
            required_skills = []

        title = _pick_first(item, ["title", "job_title", "role", "position"])
        company = _pick_first(item, ["company", "employer", "organization"]) or "Unknown"
        if not title:
            continue

        normalized.append(
            {
                "title": title,
                "company": company,
                "location": _pick_first(item, ["location", "city", "country", "work_location"]),
                "description": _pick_first(item, ["description", "summary", "job_description"]),
                "required_skills": required_skills,
                "experience_level": _pick_first(item, ["experience_level", "seniority", "level"]),
                "salary_range": _pick_first(item, ["salary_range", "salary", "compensation"]),
                "source_url": _pick_first(item, ["source_url", "url", "link", "apply_url"]),
            }
        )

    return normalized


def _jobs_from_citations(citations: list[str]) -> list[dict[str, Any]]:
    """Build minimal job cards from citation URLs as a last-resort fallback."""
    jobs: list[dict[str, Any]] = []
    for idx, url in enumerate(citations, 1):
        if not isinstance(url, str) or not url.strip():
            continue
        jobs.append(
            {
                "title": f"Opportunity Source {idx}",
                "company": "Unknown",
                "location": "",
                "description": "Open the source link to view full role details.",
                "required_skills": [],
                "experience_level": "",
                "salary_range": "",
                "source_url": url.strip(),
            }
        )
    return jobs


def _build_job_user_prompt(cv_summary: str, custom_instructions: str = "") -> str:
    """Build the user prompt with optional caller-provided constraints."""
    prompt_parts = [
        f"Candidate Profile:\n{cv_summary}",
        "Find matching job listings that are currently open.",
    ]
    instruction_text = custom_instructions.strip()
    if instruction_text:
        prompt_parts.insert(1, f"Custom instructions: {instruction_text}")
    return "\n\n".join(prompt_parts)


def search_jobs(api_key: str, cv_summary: str, custom_instructions: str = "") -> dict:
    """Search for job listings matching the candidate's profile.

    Returns:
        {"jobs": [...], "citations": [...]} on success, or {"error": str} on failure.
    """
    result = call_perplexity(
        api_key,
        JOB_RESEARCHER_SYSTEM_PROMPT,
        _build_job_user_prompt(cv_summary, custom_instructions),
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
        # Retry with a relaxed prompt that tolerates unknown fields.
        retry = call_perplexity(
            api_key,
            JOB_RESEARCHER_RELAXED_SYSTEM_PROMPT,
            _build_job_user_prompt(cv_summary, custom_instructions),
            web_search_options={"search_context_size": "high"},
        )
        if "error" not in retry:
            retry_parsed = parse_json_response(retry.get("content", ""))
            jobs = _normalize_jobs(retry_parsed)
            if jobs:
                return {
                    "jobs": jobs,
                    "citations": retry.get("citations", result.get("citations", [])),
                }

        # Last resort: still show clickable sources instead of hard-failing UX.
        fallback_jobs = _jobs_from_citations(result.get("citations", []))
        if fallback_jobs:
            return {"jobs": fallback_jobs, "citations": result.get("citations", [])}

        return {"error": "AI job search returned no valid job entries."}

    return {"jobs": jobs, "citations": result.get("citations", [])}
