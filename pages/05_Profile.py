"""Profile — user info, CV history, match history, persona switch, logout."""

from __future__ import annotations

import streamlit as st

from config.settings import PERSONAS
from utils.ui_components import clear_session, footer, page_header, require_auth, require_snowflake_session, sidebar_user_info

page_header("Profile")
user_info = require_auth()
sidebar_user_info(user_info)

session = require_snowflake_session()

user_id = st.session_state.get("user_id")

# ── User Info ────────────────────────────────────────────────────────────────
st.markdown("### 👤 Your Profile")

col1, col2 = st.columns([1, 2])

with col1:
    if user_info.get("picture"):
        st.image(user_info["picture"], width=120)

with col2:
    st.write(f"**Name:** {user_info.get('name', 'N/A')}")
    st.write(f"**Email:** {user_info.get('email', 'N/A')}")
    st.write(f"**Current Role:** {st.session_state.get('persona', 'Not selected')}")

# ── Switch Persona ───────────────────────────────────────────────────────────
st.divider()
st.markdown("### 🔄 Switch Role")

current_persona = st.session_state.get("persona", "")
new_persona = st.selectbox(
    "Change your role",
    PERSONAS,
    index=PERSONAS.index(current_persona) if current_persona in PERSONAS else 0,
)

if new_persona != current_persona:
    if st.button("Apply Role Change", type="primary"):
        st.session_state["persona"] = new_persona
        if user_id:
            session.sql(
                "UPDATE IITJ.MH.CM_USERS SET PERSONA = ? WHERE USER_ID = ?",
                params=[new_persona, user_id],
            ).collect()
        st.success(f"Role changed to **{new_persona}**!")
        st.rerun()

# ── CV History ───────────────────────────────────────────────────────────────
st.divider()
st.markdown("### 📄 CV Upload History")

if user_id:
    cv_rows = session.sql(
        "SELECT CV_ID, CV_FILE_PATH, UPLOADED_AT FROM IITJ.MH.CM_CVS "
        "WHERE USER_ID = ? ORDER BY UPLOADED_AT DESC LIMIT 10",
        params=[user_id],
    ).collect()

    if cv_rows:
        for row in cv_rows:
            cols = st.columns([3, 2, 1])
            with cols[0]:
                st.write(f"📎 {row['CV_FILE_PATH']}")
            with cols[1]:
                st.caption(str(row["UPLOADED_AT"]))
            with cols[2]:
                if st.button("🗑️ Delete", key=f"delete_cv_{row['CV_ID']}"):
                    try:
                        session.sql(
                            "DELETE FROM IITJ.MH.CM_MATCHES WHERE USER_ID = ? AND CV_ID = ?",
                            params=[user_id, int(row["CV_ID"])],
                        ).collect()
                        session.sql(
                            "DELETE FROM IITJ.MH.CM_CVS WHERE USER_ID = ? AND CV_ID = ?",
                            params=[user_id, int(row["CV_ID"])],
                        ).collect()

                        if st.session_state.get("selected_cv_id") == int(row["CV_ID"]):
                            st.session_state.pop("selected_cv_id", None)

                        st.success("CV deleted successfully. Related match history for this CV was also removed.")
                        st.rerun()
                    except Exception as exc:
                        st.error(f"Failed to delete CV: {exc}")
    else:
        st.info("No CVs uploaded yet. Go to **Upload CV** to get started.")
else:
    st.info("User ID not found. Please sign in again from the Home page.")

# ── Match History ────────────────────────────────────────────────────────────
st.divider()
st.markdown("### 📊 Match History")

if user_id:
    match_rows = session.sql(
        "SELECT m.MATCH_ID, m.TARGET_TYPE, m.TARGET_ID, m.SIMILARITY_SCORE, m.MATCHED_AT, "
        "  CASE "
        "    WHEN m.TARGET_TYPE = 'position' THEN COALESCE(p.TITLE, p.UNIVERSITY, 'Position #' || m.TARGET_ID::STRING) "
        "    WHEN m.TARGET_TYPE = 'job' THEN COALESCE(j.TITLE, j.COMPANY, 'Job #' || m.TARGET_ID::STRING) "
        "    ELSE 'Target #' || m.TARGET_ID::STRING "
        "  END AS TARGET_LABEL "
        "FROM IITJ.MH.CM_MATCHES m "
        "LEFT JOIN IITJ.MH.CM_POSITIONS p "
        "  ON m.TARGET_TYPE = 'position' AND m.TARGET_ID = p.POS_ID "
        "LEFT JOIN IITJ.MH.CM_JOBS j "
        "  ON m.TARGET_TYPE = 'job' AND m.TARGET_ID = j.JOB_ID "
        "WHERE USER_ID = ? ORDER BY MATCHED_AT DESC LIMIT 20",
        params=[user_id],
    ).collect()

    if match_rows:
        for row in match_rows:
            score = row["SIMILARITY_SCORE"]
            has_score = score is not None
            score_str = f"{float(score) * 100:.1f}%" if has_score else "N/A"
            icon = "🟢" if has_score and float(score) > 0.7 else "🟡" if has_score and float(score) > 0.5 else "🔴"

            cols = st.columns([1, 3, 2, 2])
            with cols[0]:
                st.write(f"{icon} {score_str}")
            with cols[1]:
                st.write(str(row["TARGET_LABEL"]))
            with cols[2]:
                st.write(f"Type: {row['TARGET_TYPE']}")
            with cols[3]:
                st.caption(str(row["MATCHED_AT"]))
    else:
        st.info("No matches yet. Use the dashboards to find opportunities!")
else:
    st.info("User ID not found.")

# ── Saved Drafts ─────────────────────────────────────────────────────────────
st.divider()
st.markdown("### 📝 Saved Drafts")

if user_id:
    draft_rows = session.sql(
        "SELECT DRAFT_ID, DRAFT_TYPE, CONTENT, CREATED_AT "
        "FROM IITJ.MH.CM_DRAFTS "
        "WHERE USER_ID = ? ORDER BY CREATED_AT DESC LIMIT 10",
        params=[user_id],
    ).collect()

    if draft_rows:
        for row in draft_rows:
            with st.expander(
                f"{'📝' if row['DRAFT_TYPE'] == 'SOP' else '✉️'} "
                f"{row['DRAFT_TYPE']} — {row['CREATED_AT']}"
            ):
                st.text_area(
                    "Content",
                    value=row["CONTENT"],
                    height=200,
                    key=f"draft_{row['DRAFT_ID']}",
                    disabled=True,
                )
                st.download_button(
                    "📥 Download",
                    data=row["CONTENT"],
                    file_name=f"draft_{row['DRAFT_ID']}.txt",
                    mime="text/plain",
                    key=f"dl_{row['DRAFT_ID']}",
                )
    else:
        st.info("No saved drafts. Generate SOPs or emails from the dashboards!")

# ── Logout ───────────────────────────────────────────────────────────────────
st.divider()
if st.button("🚪 Logout", type="secondary"):
    clear_session()
    st.switch_page("Home.py")

footer()
