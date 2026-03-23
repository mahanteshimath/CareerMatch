"""SOP / Email Generator — generate drafts from selected position + CV."""

from __future__ import annotations

import streamlit as st

from agents.orchestrator import orchestrate_email_generation, orchestrate_sop_generation
from utils.ui_components import footer, page_header, require_auth, require_cv, require_snowflake_session, sidebar_user_info

page_header("SOP / Email Generator")
user_info = require_auth()
sidebar_user_info(user_info)
cv_data = require_cv()

session = require_snowflake_session()

# ── Position context ─────────────────────────────────────────────────────────
position = st.session_state.get("selected_position")

if position:
    st.markdown("### 🏫 Selected Position")
    st.write(f"**{position.get('title', 'Position')}** — {position.get('university', 'University')}")
    if position.get("description"):
        with st.expander("Position Details"):
            st.write(position["description"])
else:
    st.markdown("### 🏫 Enter Position Details")
    st.caption("No position selected. Enter details manually below.")
    position = {}

# ── Manual entry / override ──────────────────────────────────────────────────
with st.expander("✏️ Edit / Enter Position Details", expanded=not position):
    pos_title = st.text_input("Position Title", value=position.get("title", ""))
    pos_university = st.text_input("University", value=position.get("university", ""))
    pos_description = st.text_area(
        "Position Description / Requirements",
        value=position.get("description", "") or position.get("requirements", ""),
        height=150,
    )
    prof_name = st.text_input(
        "Professor Name (for email)", value=position.get("professor_name", "")
    )
    prof_email = st.text_input(
        "Professor Email", value=position.get("professor_email", "")
    )

    # Update position dict
    position = {
        "title": pos_title,
        "university": pos_university,
        "description": pos_description,
        "requirements": position.get("requirements", ""),
        "professor_name": prof_name,
        "professor_email": prof_email,
    }

# ── Draft type selection ─────────────────────────────────────────────────────
st.divider()
st.markdown("### 📝 Generate Draft")

default_type = st.session_state.get("draft_type", "SOP")
draft_type = st.radio(
    "What would you like to generate?",
    ["SOP (Statement of Purpose)", "Email to Professor"],
    index=0 if default_type == "SOP" else 1,
    horizontal=True,
)

is_sop = "SOP" in draft_type

# ── Generate ─────────────────────────────────────────────────────────────────
if st.button("🚀 Generate Draft", type="primary"):
    if not position.get("title") or not position.get("university"):
        st.error("Please provide at least a Position Title and University.")
        st.stop()

    if is_sop:
        position_details = (
            f"Position: {position['title']}\n"
            f"University: {position['university']}\n"
            f"Description: {position.get('description', '')}\n"
            f"Requirements: {position.get('requirements', '')}"
        )
        with st.spinner("Generating SOP draft... This may take a moment."):
            result = orchestrate_sop_generation(
                session, cv_data, position_details, "SOP"
            )
            if isinstance(result, dict) and "error" in result:
                st.error(f"SOP generation failed: {result['error']}")
                st.stop()
            draft = result.get("content", "") if isinstance(result, dict) else str(result)
            st.session_state["generated_draft"] = draft
            st.session_state["generated_draft_type"] = "SOP"
    else:
        if not position.get("professor_name"):
            st.error("Please provide the Professor's name for the email.")
            st.stop()
        with st.spinner("Generating email draft..."):
            result = orchestrate_email_generation(
                session,
                cv_data,
                position["title"],
                position["university"],
                position["professor_name"],
            )
            if isinstance(result, dict) and "error" in result:
                st.error(f"Email generation failed: {result['error']}")
                st.stop()
            draft = result.get("content", "") if isinstance(result, dict) else str(result)
            st.session_state["generated_draft"] = draft
            st.session_state["generated_draft_type"] = "Email"

# ── Display draft ────────────────────────────────────────────────────────────
if st.session_state.get("generated_draft"):
    draft = st.session_state["generated_draft"]
    draft_label = st.session_state.get("generated_draft_type", "Draft")

    st.divider()
    st.markdown(f"### ✅ Generated {draft_label}")

    st.text_area(
        f"Your {draft_label} Draft",
        value=draft,
        height=400,
        key="draft_display",
    )

    col1, col2, col3 = st.columns(3)
    with col1:
        st.download_button(
            label=f"📥 Download {draft_label}",
            data=draft,
            file_name=f"careermatch_{draft_label.lower()}_{position.get('university', 'draft')}.txt",
            mime="text/plain",
        )
    with col2:
        if st.button("🔄 Regenerate"):
            del st.session_state["generated_draft"]
            st.rerun()
    with col3:
        # Save to Snowflake
        if st.button("💾 Save Draft"):
            user_id = st.session_state.get("user_id")
            if user_id:
                session.sql(
                    "INSERT INTO IITJ.MH.CM_DRAFTS (USER_ID, DRAFT_TYPE, CONTENT) "
                    "VALUES (?, ?, ?)",
                    params=[user_id, draft_label, draft],
                ).collect()
                st.success("Draft saved!")

    st.warning(
        "⚠️ **Disclaimer:** This is an AI-generated draft. "
        "Please review, personalize, and verify all content before sending. "
        "For personalized, one-to-one support, check the available packages with the team."
    )

footer()
