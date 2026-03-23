"""Multi-agent orchestrator — chains agents, manages caching, and coordinates workflows."""

from __future__ import annotations

import hashlib
import json
import logging
import os
from datetime import datetime, timedelta

import streamlit as st
from snowflake.snowpark import Session

from config.settings import CORTEX_EMBED_MODEL
from agents.cv_parser import parse_cv
from agents.position_researcher import search_positions
from agents.job_researcher import search_jobs
from agents.sop_writer import generate_sop, generate_email
from agents.skill_analyzer import analyze_skill_gap


logger = logging.getLogger(__name__)


def _get_api_key() -> str:
    """Retrieve Perplexity API key from Streamlit secrets or environment.

    Supports multiple key layouts to avoid runtime breakage across deployments.
    """
    def _normalize(value: object) -> str | None:
        if value is None:
            return None
        text = str(value).strip().strip('"').strip("'")
        return text or None

    # Preferred nested layout: [api_keys] perplexity = "..."
    try:
        api_keys = st.secrets.get("api_keys")
        if api_keys is not None:
            key = None
            # Works for dict-like secret sections.
            if hasattr(api_keys, "get"):
                key = api_keys.get("perplexity")
            # Works for Streamlit section objects supporting index access.
            if not key:
                try:
                    key = api_keys["perplexity"]
                except Exception:
                    pass
            normalized = _normalize(key)
            if normalized:
                return normalized
    except Exception:
        pass

    # Common flat secret names used in Streamlit apps.
    for secret_name in ("PERPLEXITY_API_KEY", "perplexity_api_key", "perplexity"):
        try:
            value = st.secrets.get(secret_name)
            normalized = _normalize(value)
            if normalized:
                return normalized
        except Exception:
            continue

    # Environment fallback for local/dev execution.
    for env_name in ("PERPLEXITY_API_KEY", "PPLX_API_KEY", "PERPLEXITY_KEY"):
        normalized = _normalize(os.getenv(env_name))
        if normalized:
            return normalized

    raise KeyError(
        "Perplexity API key not found. Configure one of: "
        "st.secrets['api_keys']['perplexity'], st.secrets['PERPLEXITY_API_KEY'], "
        "or env PERPLEXITY_API_KEY."
    )


def _cache_key(agent_name: str, query: str) -> str:
    """Generate a deterministic cache key."""
    return hashlib.sha256(f"{agent_name}:{query}".encode()).hexdigest()


def _check_cache(session: Session, agent_name: str, query: str) -> str | None:
    """Check Snowflake cache for a previous agent response."""
    key = _cache_key(agent_name, query)
    try:
        rows = session.sql(
            "SELECT RESPONSE FROM IITJ.MH.CM_AGENT_CACHE "
            "WHERE AGENT_NAME = ? AND QUERY_HASH = ? AND EXPIRES_AT > CURRENT_TIMESTAMP()",
            params=[agent_name, key],
        ).collect()
        if rows:
            return rows[0]["RESPONSE"]
    except Exception as exc:
        logger.warning(
            "cache_lookup_failed",
            extra={"agent_name": agent_name, "error": str(exc)},
        )
    return None


def _store_cache(
    session: Session, agent_name: str, query: str, response: str, ttl_hours: int = 24
) -> None:
    """Store an agent response in Snowflake cache."""
    key = _cache_key(agent_name, query)
    expires = datetime.utcnow() + timedelta(hours=ttl_hours)
    try:
        session.sql(
            "INSERT INTO IITJ.MH.CM_AGENT_CACHE (AGENT_NAME, QUERY_HASH, RESPONSE, EXPIRES_AT) "
            "VALUES (?, ?, ?, ?)",
            params=[agent_name, key, response, expires.isoformat()],
        ).collect()
    except Exception as exc:
        logger.warning(
            "cache_store_failed",
            extra={"agent_name": agent_name, "error": str(exc)},
        )


def validate_perplexity_key() -> tuple[bool, str | None]:
    """Validate that a Perplexity API key is configured and readable."""
    try:
        _get_api_key()
        return True, None
    except KeyError as exc:
        return False, str(exc)


def orchestrate_cv_parsing(session: Session, cv_text: str) -> dict:
    """Parse CV text, caching the result."""
    cached = _check_cache(session, "cv_parser", cv_text[:500])
    if cached:
        try:
            return json.loads(cached)
        except json.JSONDecodeError:
            pass

    result = parse_cv(_get_api_key(), cv_text)
    if "error" not in result:
        _store_cache(session, "cv_parser", cv_text[:500], json.dumps(result))
    return result


def orchestrate_position_search(
    session: Session,
    cv_data: dict,
    position_type: str,
    continent: str,
) -> dict:
    """Search for university positions, caching results.

    Returns:
        {"positions": [...], "citations": [...]} on success, or {"error": str}.
    """
    cv_summary = _build_cv_summary(cv_data)
    cache_query = f"{cv_summary[:200]}|{position_type}|{continent}"

    cached = _check_cache(session, "position_researcher", cache_query)
    if cached:
        try:
            data = json.loads(cached)
            if isinstance(data, list):
                # Legacy cache shape: bare list. Treat empty list as stale cache.
                if data:
                    return {"positions": data, "citations": []}
                data = None
            # Current cache shape: {"positions": [...], "citations": [...]}.
            if isinstance(data, dict) and "positions" in data:
                positions = data.get("positions", [])
                if isinstance(positions, list) and positions:
                    return data
                # Empty cached positions should not block a fresh AI search.
                data = None

            if data:
                return data
        except json.JSONDecodeError:
            pass

    current_date = datetime.utcnow().strftime("%Y-%m-%d")
    try:
        api_key = _get_api_key()
    except KeyError as e:
        return {"error": str(e)}

    try:
        result = search_positions(
            api_key, cv_summary, position_type, continent, current_date
        )
    except Exception as e:
        return {"error": f"Unexpected error during position search: {e}"}

    if "error" in result:
        return result

    # Store results in CM_POSITIONS table for vector matching
    for pos in result.get("positions", []):
        _upsert_position(session, pos)

    # Avoid persisting empty payloads; they cause confusing UX on cache hits.
    if result.get("positions"):
        _store_cache(session, "position_researcher", cache_query, json.dumps(result))
    return result


def orchestrate_job_search(session: Session, cv_data: dict) -> dict:
    """Search for job listings, caching results.

    Returns:
        {"jobs": [...], "citations": [...]} on success, or {"error": str}.
    """
    cv_summary = _build_cv_summary(cv_data)
    cache_query = cv_summary[:300]

    cached = _check_cache(session, "job_researcher", cache_query)
    if cached:
        try:
            data = json.loads(cached)
            if isinstance(data, list):
                # Legacy cache shape: bare list. Treat empty list as stale cache.
                if data:
                    return {"jobs": data, "citations": []}
                data = None
            # Current cache shape: {"jobs": [...], "citations": [...]}.
            if isinstance(data, dict) and "jobs" in data:
                jobs = data.get("jobs", [])
                if isinstance(jobs, list) and jobs:
                    return data
                # Empty cached jobs should not block a fresh AI search.
                data = None

            if data:
                return data
        except json.JSONDecodeError:
            pass

    try:
        api_key = _get_api_key()
    except KeyError as e:
        return {"error": str(e)}

    try:
        result = search_jobs(api_key, cv_summary)
    except Exception as e:
        return {"error": f"Unexpected error during job search: {e}"}

    if "error" in result:
        return result

    for job in result.get("jobs", []):
        _upsert_job(session, job)

    # Avoid persisting empty payloads; they cause confusing UX on cache hits.
    if result.get("jobs"):
        _store_cache(session, "job_researcher", cache_query, json.dumps(result))
    return result


def orchestrate_sop_generation(
    session: Session,
    cv_data: dict,
    position_details: str,
    draft_type: str = "SOP",
) -> dict:
    """Generate SOP or email draft.

    Returns:
        {"content": str} on success, or {"error": str}.
    """
    cv_summary = _build_cv_summary(cv_data)
    try:
        api_key = _get_api_key()
    except KeyError as e:
        return {"error": str(e)}

    return generate_sop(api_key, cv_summary, position_details, draft_type)


def orchestrate_email_generation(
    session: Session,
    cv_data: dict,
    position_title: str,
    university: str,
    professor_name: str,
) -> dict:
    """Generate email draft.

    Returns:
        {"content": str} on success, or {"error": str}.
    """
    cv_summary = _build_cv_summary(cv_data)
    try:
        api_key = _get_api_key()
    except KeyError as e:
        return {"error": str(e)}

    return generate_email(
        api_key, cv_summary, position_title, university, professor_name
    )


def orchestrate_skill_analysis(
    session: Session,
    cv_data: dict,
    job_description: str,
    job_required_skills: list[str],
) -> dict:
    """Analyze skill gap between CV and job.

    Returns:
        Skill gap dict on success, or {"error": str}.
    """
    candidate_skills = cv_data.get("skills", [])
    try:
        api_key = _get_api_key()
    except KeyError as e:
        return {"error": str(e)}

    return analyze_skill_gap(
        api_key, candidate_skills, job_description, job_required_skills
    )


def _build_cv_summary(cv_data: dict) -> str:
    """Build a concise text summary from parsed CV data for agent prompts."""
    parts = []
    if cv_data.get("name"):
        parts.append(f"Name: {cv_data['name']}")
    if cv_data.get("summary"):
        parts.append(f"Summary: {cv_data['summary']}")
    if cv_data.get("education"):
        edu_lines = [
            f"- {e.get('degree', '')} in {e.get('field', '')} from {e.get('institution', '')} ({e.get('year', '')})"
            for e in cv_data["education"]
        ]
        parts.append("Education:\n" + "\n".join(edu_lines))
    if cv_data.get("skills"):
        parts.append(f"Skills: {', '.join(cv_data['skills'])}")
    if cv_data.get("experience"):
        exp_lines = [
            f"- {e.get('title', '')} at {e.get('company', '')} ({e.get('duration', '')})"
            for e in cv_data["experience"]
        ]
        parts.append("Experience:\n" + "\n".join(exp_lines))
    if cv_data.get("research_interests"):
        parts.append(f"Research Interests: {', '.join(cv_data['research_interests'])}")
    if cv_data.get("publications"):
        parts.append(f"Publications: {len(cv_data['publications'])} papers")
    return "\n\n".join(parts)


def _upsert_position(session: Session, pos: dict) -> None:
    """Insert a position into the CM_POSITIONS table if not already present."""
    title = pos.get("title", "")
    university = pos.get("university", "")
    if not title or not university:
        return

    try:
        existing = session.sql(
            "SELECT POS_ID FROM IITJ.MH.CM_POSITIONS WHERE TITLE = ? AND UNIVERSITY = ?",
            params=[title, university],
        ).collect()
        if existing:
            return

        session.sql(
            "INSERT INTO IITJ.MH.CM_POSITIONS "
            "(TITLE, UNIVERSITY, COUNTRY, CONTINENT, POSITION_TYPE, DEADLINE, "
            "DESCRIPTION, REQUIREMENTS, PROFESSOR_NAME, PROFESSOR_EMAIL, SOURCE_URL, EMBEDDING) "
            "VALUES (?, ?, ?, ?, ?, TRY_TO_DATE(?), ?, ?, ?, ?, ?, "
            "SNOWFLAKE.CORTEX.EMBED_TEXT_768(?, ?))",
            params=[
                title,
                university,
                pos.get("country", ""),
                pos.get("continent", ""),
                pos.get("position_type", ""),
                pos.get("deadline", ""),
                pos.get("description", ""),
                pos.get("requirements", ""),
                pos.get("professor_name", ""),
                pos.get("professor_email", ""),
                pos.get("source_url", ""),
                CORTEX_EMBED_MODEL,
                (
                    f"{title}\n"
                    f"{pos.get('description', '')}\n"
                    f"{pos.get('requirements', '')}"
                )[:8000],
            ],
        ).collect()
    except Exception as exc:
        logger.warning(
            "position_upsert_failed",
            extra={
                "title": title,
                "university": university,
                "error": str(exc),
            },
        )
        # DB persistence should not block showing AI results in UI.
        return


def _upsert_job(session: Session, job: dict) -> None:
    """Insert a job into the CM_JOBS table if not already present."""
    title = job.get("title", "")
    company = job.get("company", "")
    if not title or not company:
        return

    try:
        existing = session.sql(
            "SELECT JOB_ID FROM IITJ.MH.CM_JOBS WHERE TITLE = ? AND COMPANY = ?",
            params=[title, company],
        ).collect()
        if existing:
            return

        required_skills = job.get("required_skills", [])
        if isinstance(required_skills, list):
            required_skills = ", ".join(required_skills)

        session.sql(
            "INSERT INTO IITJ.MH.CM_JOBS "
            "(TITLE, COMPANY, LOCATION, DESCRIPTION, REQUIRED_SKILLS, "
            "EXPERIENCE_LEVEL, SALARY_RANGE, SOURCE_URL, EMBEDDING) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, SNOWFLAKE.CORTEX.EMBED_TEXT_768(?, ?))",
            params=[
                title,
                company,
                job.get("location", ""),
                job.get("description", ""),
                required_skills,
                job.get("experience_level", ""),
                job.get("salary_range", ""),
                job.get("source_url", ""),
                CORTEX_EMBED_MODEL,
                (
                    f"{title}\n"
                    f"{job.get('description', '')}\n"
                    f"Required skills: {required_skills}"
                )[:8000],
            ],
        ).collect()
    except Exception as exc:
        logger.warning(
            "job_upsert_failed",
            extra={"title": title, "company": company, "error": str(exc)},
        )
        # DB persistence should not block showing AI results in UI.
        return
