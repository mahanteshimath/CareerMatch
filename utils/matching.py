"""Similarity scoring and ranking utilities using Snowflake Cortex EMBED_TEXT."""

from __future__ import annotations

from snowflake.snowpark import Session

from config.settings import CORTEX_EMBED_MODEL


def compute_embedding(session: Session, text: str) -> list[float]:
    """Generate an embedding vector for the given text via Snowflake Cortex."""
    result = session.sql(
        "SELECT SNOWFLAKE.CORTEX.EMBED_TEXT_768(?, ?) AS EMB",
        params=[CORTEX_EMBED_MODEL, text[:8000]],
    ).collect()
    return result[0]["EMB"]


def match_positions(
    session: Session, cv_text: str, filters: dict, top_k: int = 10
) -> list[dict]:
    """Match CV against university positions using vector similarity.

    Args:
        session: Snowflake session
        cv_text: Raw text extracted from CV
        filters: Dict with keys like position_type, continent
        top_k: Number of top matches to return
    """
    where_clauses = ["1=1"]
    params: list = []

    if filters.get("position_type"):
        where_clauses.append("POSITION_TYPE = ?")
        params.append(filters["position_type"])
    if filters.get("continent"):
        where_clauses.append("CONTINENT = ?")
        params.append(filters["continent"])
    if filters.get("open_only"):
        where_clauses.append("DEADLINE >= CURRENT_DATE()")

    where_sql = " AND ".join(where_clauses)

    query = f"""
        SELECT POS_ID, TITLE, UNIVERSITY, COUNTRY, CONTINENT, POSITION_TYPE,
               DEADLINE, DESCRIPTION, REQUIREMENTS, PROFESSOR_NAME,
               PROFESSOR_EMAIL, SOURCE_URL,
               VECTOR_COSINE_SIMILARITY(
                   EMBEDDING,
                   SNOWFLAKE.CORTEX.EMBED_TEXT_768(?, ?)
               ) AS SIMILARITY
        FROM IITJ.MH.CM_POSITIONS
        WHERE {where_sql}
          AND EMBEDDING IS NOT NULL
        ORDER BY SIMILARITY DESC
        LIMIT ?
    """  # noqa: S608

    all_params = [CORTEX_EMBED_MODEL, cv_text[:8000]] + params + [top_k]
    rows = session.sql(query, params=all_params).collect()
    return [row.as_dict() for row in rows]


def match_jobs(
    session: Session, cv_text: str, top_k: int = 10
) -> list[dict]:
    """Match CV against job listings using vector similarity."""
    query = """
        SELECT JOB_ID, TITLE, COMPANY, LOCATION, DESCRIPTION,
               REQUIRED_SKILLS, EXPERIENCE_LEVEL, SALARY_RANGE, SOURCE_URL,
               VECTOR_COSINE_SIMILARITY(
                   EMBEDDING,
                   SNOWFLAKE.CORTEX.EMBED_TEXT_768(?, ?)
               ) AS SIMILARITY
        FROM IITJ.MH.CM_JOBS
        WHERE EMBEDDING IS NOT NULL
        ORDER BY SIMILARITY DESC
        LIMIT ?
    """  # noqa: S608

    rows = session.sql(
        query, params=[CORTEX_EMBED_MODEL, cv_text[:8000], top_k]
    ).collect()
    return [row.as_dict() for row in rows]
