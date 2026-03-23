"""CareerMatch — Entry point: Google auth, Snowflake init, persona routing."""

from __future__ import annotations

import streamlit as st

from config.settings import (
    APP_DESCRIPTION,
    APP_ICON,
    APP_NAME,
    PERSONA_JOB_SEEKER,
    PERSONA_STUDENT,
)
from utils.auth import ensure_user_in_db, google_login
from utils.snowflake_utils import init_snowflake

st.set_page_config(page_title=APP_NAME, page_icon=APP_ICON, layout="wide")

# ── Snowflake init ───────────────────────────────────────────────────────────
session = init_snowflake()
st.session_state["snowflake_session"] = session

# ── Header ───────────────────────────────────────────────────────────────────
st.title(f"{APP_ICON} {APP_NAME}")
st.subheader(APP_DESCRIPTION)

# ── Google Sign-in (built-in Streamlit auth) ─────────────────────────────────
user_info = google_login()

if user_info is None:
    st.header("This app is private.")
    st.subheader("Please log in to continue.")
    st.button("Log in with Google", on_click=st.login)
    st.stop()

# Store in session
st.session_state["user_info_dict"] = user_info

# ── Sidebar: user info ──────────────────────────────────────────────────────
with st.sidebar:
    if user_info.get("picture"):
        st.image(user_info["picture"], width=60)
    st.write(f"**{user_info.get('name', 'User')}**")
    st.caption(user_info.get("email", ""))
    st.button("Log out", on_click=st.logout)

# ── Persona selection ────────────────────────────────────────────────────────
st.divider()
st.markdown("### Choose your path")

col1, col2 = st.columns(2)

with col1:
    st.markdown("#### 🎓 Student")
    st.markdown(
        "Find **Masters, PhD & Postdoc** positions worldwide. "
        "Upload your CV, filter by program type and continent, "
        "and generate SOP/email drafts."
    )
    if st.button("Continue as Student", type="primary", use_container_width=True):
        st.session_state["persona"] = PERSONA_STUDENT
        user_id = ensure_user_in_db(session, user_info, PERSONA_STUDENT)
        st.session_state["user_id"] = user_id
        st.switch_page("pages/01_Upload_CV.py")

with col2:
    st.markdown("#### 💼 Job Seeker")
    st.markdown(
        "Find **matching jobs** based on your skills and experience. "
        "Get similarity scores, identify skill gaps, "
        "and receive actionable career insights."
    )
    if st.button("Continue as Job Seeker", type="primary", use_container_width=True):
        st.session_state["persona"] = PERSONA_JOB_SEEKER
        user_id = ensure_user_in_db(session, user_info, PERSONA_JOB_SEEKER)
        st.session_state["user_id"] = user_id
        st.switch_page("pages/01_Upload_CV.py")

# ── Show current persona if already selected ─────────────────────────────────
if st.session_state.get("persona"):
    persona = st.session_state["persona"]
    st.sidebar.info(f"Role: {persona}")

# ── Footer ───────────────────────────────────────────────────────────────────
st.divider()
st.caption(f"© 2026 {APP_NAME} — AI-powered CV-to-opportunity matching")
