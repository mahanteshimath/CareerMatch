"""Snowflake connection, session management, and auto-schema creation."""

import streamlit as st
from snowflake.snowpark import Session
from snowflake.snowpark.context import get_active_session


def get_snowflake_session() -> Session:
    """Get Snowflake session — works both locally and in Streamlit-in-Snowflake."""
    try:
        return get_active_session()
    except Exception:
        return st.connection("snowflake").session()


@st.cache_resource
def init_snowflake() -> Session:
    """Initialize Snowflake connection and create schema objects on first run."""
    session = get_snowflake_session()
    _create_stage(session)
    _create_tables(session)
    _ensure_performance_objects(session)
    _cleanup_expired_cache(session)
    return session


def _create_stage(session: Session) -> None:
    """Create the file stage if it doesn't exist."""
    session.sql(
        "CREATE STAGE IF NOT EXISTS IITJ.MH.CAREERMATCH_STAGE "
        "ENCRYPTION = (TYPE = 'SNOWFLAKE_SSE')"
    ).collect()


def _create_tables(session: Session) -> None:
    """Auto-create all application tables on first run."""
    ddl_statements = [
        """
        CREATE TABLE IF NOT EXISTS IITJ.MH.CM_USERS (
            USER_ID       NUMBER AUTOINCREMENT PRIMARY KEY,
            EMAIL         VARCHAR NOT NULL UNIQUE,
            DISPLAY_NAME  VARCHAR,
            PERSONA       VARCHAR,
            GOOGLE_SUB    VARCHAR,
            CREATED_AT    TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP()
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS IITJ.MH.CM_CVS (
            CV_ID         NUMBER AUTOINCREMENT PRIMARY KEY,
            USER_ID       NUMBER NOT NULL,
            CV_FILE_PATH  VARCHAR NOT NULL,
            PARSED_JSON   VARIANT,
            UPLOADED_AT   TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP()
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS IITJ.MH.CM_POSITIONS (
            POS_ID          NUMBER AUTOINCREMENT PRIMARY KEY,
            TITLE           VARCHAR,
            UNIVERSITY      VARCHAR,
            COUNTRY         VARCHAR,
            CONTINENT       VARCHAR,
            POSITION_TYPE   VARCHAR,
            DEADLINE        DATE,
            DESCRIPTION     VARCHAR(16777216),
            REQUIREMENTS    VARCHAR(16777216),
            PROFESSOR_NAME  VARCHAR,
            PROFESSOR_EMAIL VARCHAR,
            SOURCE_URL      VARCHAR,
            EMBEDDING       VECTOR(FLOAT, 768),
            CREATED_AT      TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP()
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS IITJ.MH.CM_JOBS (
            JOB_ID          NUMBER AUTOINCREMENT PRIMARY KEY,
            TITLE           VARCHAR,
            COMPANY         VARCHAR,
            LOCATION        VARCHAR,
            DESCRIPTION     VARCHAR(16777216),
            REQUIRED_SKILLS VARCHAR(16777216),
            EXPERIENCE_LEVEL VARCHAR,
            SALARY_RANGE    VARCHAR,
            SOURCE_URL      VARCHAR,
            EMBEDDING       VECTOR(FLOAT, 768),
            CREATED_AT      TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP()
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS IITJ.MH.CM_MATCHES (
            MATCH_ID        NUMBER AUTOINCREMENT PRIMARY KEY,
            USER_ID         NUMBER NOT NULL,
            CV_ID           NUMBER NOT NULL,
            TARGET_TYPE     VARCHAR,
            TARGET_ID       NUMBER,
            SIMILARITY_SCORE FLOAT,
            MISSING_SKILLS  VARCHAR(16777216),
            MATCHED_AT      TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP()
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS IITJ.MH.CM_DRAFTS (
            DRAFT_ID      NUMBER AUTOINCREMENT PRIMARY KEY,
            USER_ID       NUMBER NOT NULL,
            MATCH_ID      NUMBER,
            DRAFT_TYPE    VARCHAR,
            CONTENT       VARCHAR(16777216),
            CREATED_AT    TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP()
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS IITJ.MH.CM_AGENT_CACHE (
            CACHE_ID      NUMBER AUTOINCREMENT PRIMARY KEY,
            AGENT_NAME    VARCHAR,
            QUERY_HASH    VARCHAR,
            RESPONSE      VARCHAR(16777216),
            CREATED_AT    TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP(),
            EXPIRES_AT    TIMESTAMP_NTZ
        )
        """,
    ]
    for ddl in ddl_statements:
        session.sql(ddl).collect()


def _ensure_performance_objects(session: Session) -> None:
    """Ensure runtime schema has perf-critical columns and search optimization."""
    session.sql(
        "ALTER TABLE IITJ.MH.CM_POSITIONS "
        "ADD COLUMN IF NOT EXISTS EMBEDDING VECTOR(FLOAT, 768)"
    ).collect()
    session.sql(
        "ALTER TABLE IITJ.MH.CM_JOBS "
        "ADD COLUMN IF NOT EXISTS EMBEDDING VECTOR(FLOAT, 768)"
    ).collect()

    optimization_statements = [
        "ALTER TABLE IITJ.MH.CM_AGENT_CACHE "
        "ADD SEARCH OPTIMIZATION ON EQUALITY(AGENT_NAME, QUERY_HASH)",
        "ALTER TABLE IITJ.MH.CM_POSITIONS "
        "ADD SEARCH OPTIMIZATION ON EQUALITY(POSITION_TYPE, CONTINENT, TITLE, UNIVERSITY)",
        "ALTER TABLE IITJ.MH.CM_JOBS "
        "ADD SEARCH OPTIMIZATION ON EQUALITY(TITLE, COMPANY)",
    ]
    for stmt in optimization_statements:
        try:
            session.sql(stmt).collect()
        except Exception:
            # Keep startup idempotent when optimization is already configured.
            continue


def _cleanup_expired_cache(session: Session) -> None:
    """Delete expired cache rows to avoid unbounded table growth."""
    session.sql(
        "DELETE FROM IITJ.MH.CM_AGENT_CACHE "
        "WHERE EXPIRES_AT IS NOT NULL AND EXPIRES_AT < CURRENT_TIMESTAMP()"
    ).collect()
