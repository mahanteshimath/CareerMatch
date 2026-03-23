"""Google OAuth helpers for Streamlit.

Uses Streamlit's built-in authentication (st.login / st.logout / st.user)
which is available since Streamlit 1.42.0 with Authlib.
Secrets are read from .streamlit/secrets.toml → [auth] section.
"""

from __future__ import annotations

import streamlit as st


def google_login() -> dict | None:
    """Check if user is logged in via Streamlit's built-in auth.

    Returns dict with keys: email, name, picture, sub (Google subject ID),
    or None if not authenticated.
    """
    if not st.user.is_logged_in:
        return None

    return {
        "email": st.user.get("email", ""),
        "name": st.user.get("name", ""),
        "picture": st.user.get("picture", ""),
        "sub": st.user.get("sub", ""),
    }


def ensure_user_in_db(session, user_info: dict, persona: str) -> int:
    """Upsert user record in Snowflake. Returns USER_ID."""
    existing = session.sql(
        "SELECT USER_ID FROM IITJ.MH.CM_USERS WHERE EMAIL = ?",
        params=[user_info["email"]],
    ).collect()

    if existing:
        return existing[0]["USER_ID"]

    session.sql(
        "INSERT INTO IITJ.MH.CM_USERS (EMAIL, DISPLAY_NAME, PERSONA, GOOGLE_SUB) "
        "VALUES (?, ?, ?, ?)",
        params=[user_info["email"], user_info["name"], persona, user_info["sub"]],
    ).collect()

    result = session.sql(
        "SELECT USER_ID FROM IITJ.MH.CM_USERS WHERE EMAIL = ?",
        params=[user_info["email"]],
    ).collect()
    return result[0]["USER_ID"]
