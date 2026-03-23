"""Agent: identify skill gaps between CV and job requirements."""

from __future__ import annotations

from utils.perplexity_client import call_perplexity, parse_json_response

SKILL_ANALYZER_SYSTEM_PROMPT = """You are a career skills gap analyst. Given a candidate's
skills (from their CV) and a job description's required skills, identify:

1. **Matching skills**: Skills the candidate already has that match the job
2. **Missing skills**: Skills required by the job that the candidate lacks
3. **Transferable skills**: Skills the candidate has that could be applied differently
4. **Recommendations**: Specific, actionable steps to fill the gaps

Return ONLY valid JSON:
{
    "matching_skills": ["skill1", "skill2"],
    "missing_skills": ["skill3", "skill4"],
    "transferable_skills": [
        {"skill": "existing_skill", "application": "how it transfers"}
    ],
    "match_percentage": 75,
    "recommendations": [
        "Take course X to learn skill Y",
        "Build a project demonstrating skill Z"
    ],
    "overall_assessment": "Brief 2-3 sentence assessment of the candidate's fit"
}

Return ONLY the JSON, no markdown or explanation."""


def analyze_skill_gap(
    api_key: str,
    candidate_skills: list[str],
    job_description: str,
    job_required_skills: list[str],
) -> dict:
    """Analyze skill gap between candidate and job requirements.

    Returns:
        Skill gap analysis dict on success, or {"error": str} on failure.
    """
    user_prompt = (
        f"CANDIDATE SKILLS:\n{', '.join(candidate_skills)}\n\n"
        f"JOB DESCRIPTION:\n{job_description}\n\n"
        f"REQUIRED SKILLS:\n{', '.join(job_required_skills)}\n\n"
        f"Analyze the skill gap."
    )
    result = call_perplexity(api_key, SKILL_ANALYZER_SYSTEM_PROMPT, user_prompt)
    if "error" in result:
        return result

    parsed = parse_json_response(result["content"])
    if parsed is None:
        return {"error": "Failed to parse skill analysis: AI returned invalid JSON."}
    return parsed
