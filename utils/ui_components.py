"""Shared Streamlit UI widgets for CareerMatch."""

from __future__ import annotations

import streamlit as st
from config.settings import APP_NAME, APP_ICON


def page_header(title: str, icon: str = APP_ICON) -> None:
    """Render a consistent page header."""
    st.set_page_config(page_title=f"{APP_NAME} — {title}", page_icon=icon, layout="wide")
    st.title(f"{icon} {title}")


def require_auth() -> dict | None:
    """Check if user is authenticated. Returns user_info dict or shows warning."""
    # First check Streamlit's built-in auth
    if st.user.is_logged_in:
        user_info = {
            "email": st.user.get("email", ""),
            "name": st.user.get("name", ""),
            "picture": st.user.get("picture", ""),
            "sub": st.user.get("sub", ""),
        }
        st.session_state["user_info_dict"] = user_info
        return user_info
    # Fallback to session state (shouldn't normally reach here)
    user_info = st.session_state.get("user_info_dict")
    if not user_info:
        st.warning("Please sign in from the Home page first.")
        st.stop()
    return user_info


def require_cv() -> dict | None:
    """Check session state for an uploaded CV. Returns parsed CV data or shows warning."""
    cv_data = st.session_state.get("parsed_cv")
    if not cv_data:
        st.warning("Please upload your CV first (Upload CV page).")
        st.stop()
    return cv_data


def require_snowflake_session():
    """Check session state for a Snowflake session. Returns session or stops with error."""
    session = st.session_state.get("snowflake_session")
    if not session:
        st.error("Snowflake session not found. Please go to the Home page first.")
        st.stop()
    return session


def clear_session() -> None:
    """Clear all CareerMatch session state keys and log out."""
    static_keys = [
        "user_info_dict", "user_id", "persona", "parsed_cv", "cv_text",
        "cv_stage_path", "ai_positions", "ai_jobs", "db_position_matches",
        "db_job_matches", "generated_draft", "generated_draft_type",
        "selected_position", "draft_type", "snowflake_session",
    ]
    # Also clear any dynamically-generated skill analysis keys
    dynamic_keys = [k for k in st.session_state if k.startswith(("skill_analysis_", "db_skill_analysis_"))]
    for key in static_keys + dynamic_keys:
        st.session_state.pop(key, None)
    st.logout()


def sidebar_user_info(user_info: dict) -> None:
    """Display user info in the sidebar."""
    with st.sidebar:
        if user_info.get("picture"):
            st.image(user_info["picture"], width=60)
        st.write(f"**{user_info.get('name', 'User')}**")
        st.caption(user_info.get("email", ""))
        persona = st.session_state.get("persona", "Not set")
        st.info(f"Role: {persona}")


def footer() -> None:
    """Render a consistent footer."""
    st.divider()
    st.caption(f"© 2026 {APP_NAME} — AI-powered CV-to-opportunity matching")
