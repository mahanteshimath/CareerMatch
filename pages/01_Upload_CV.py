"""Upload CV — file upload, text extraction, AI parsing."""

from __future__ import annotations

import json

import streamlit as st

from agents.orchestrator import orchestrate_cv_parsing
from config.settings import ALLOWED_CV_EXTENSIONS, MAX_CV_SIZE_MB, PERSONA_STUDENT
from utils.cv_utils import extract_text_from_pdf, stage_cv, validate_cv
from utils.ui_components import footer, page_header, require_auth, require_snowflake_session, sidebar_user_info

page_header("Upload CV")
user_info = require_auth()
sidebar_user_info(user_info)

session = require_snowflake_session()

# ── Upload section ───────────────────────────────────────────────────────────
st.markdown("### 📄 Upload your CV")
st.caption(
    f"Supported formats: {', '.join(ALLOWED_CV_EXTENSIONS)} — Max size: {MAX_CV_SIZE_MB} MB"
)

uploaded_file = st.file_uploader(
    "Choose your CV",
    type=[ext.lstrip(".") for ext in ALLOWED_CV_EXTENSIONS],
    key="cv_uploader",
)

if uploaded_file:
    error = validate_cv(uploaded_file)
    if error:
        st.error(error)
        st.stop()

    st.success(f"✅ {uploaded_file.name} uploaded successfully!")

    # Extract text
    with st.spinner("Extracting text from CV..."):
        cv_text = extract_text_from_pdf(uploaded_file)

    if not cv_text.strip():
        st.error("Could not extract text from the PDF. Please ensure it's not a scanned image.")
        st.stop()

    st.session_state["cv_text"] = cv_text

    with st.expander("📝 Extracted Text Preview", expanded=False):
        st.text(cv_text[:2000] + ("..." if len(cv_text) > 2000 else ""))

    # Stage file in Snowflake
    user_id = st.session_state.get("user_id")
    if user_id:
        with st.spinner("Staging CV in Snowflake..."):
            uploaded_file.seek(0)
            stage_path = stage_cv(session, uploaded_file, user_id)
            st.session_state["cv_stage_path"] = stage_path

    # AI Parsing
    st.divider()
    st.markdown("### 🤖 AI-Powered CV Parsing")

    if st.button("Parse CV with AI", type="primary"):
        with st.spinner("AI is analyzing your CV... This may take a moment."):
            parsed = orchestrate_cv_parsing(session, cv_text)
            if isinstance(parsed, dict) and "error" in parsed:
                st.error(f"CV parsing failed: {parsed['error']}")
            else:
                st.session_state["parsed_cv"] = parsed
                # Store in Snowflake
                if user_id:
                    try:
                        session.sql(
                            "INSERT INTO IITJ.MH.CM_CVS (USER_ID, CV_FILE_PATH, PARSED_JSON) "
                            "SELECT ?, ?, PARSE_JSON(?)",
                            params=[user_id, stage_path, json.dumps(parsed)],
                        ).collect()
                    except Exception as e:
                        st.warning(f"CV parsed but failed to save: {e}")

    # Display parsed results
    if st.session_state.get("parsed_cv"):
        parsed = st.session_state["parsed_cv"]
        st.success("CV parsed successfully!")

        col1, col2 = st.columns(2)

        with col1:
            st.markdown("#### 👤 Personal Info")
            st.write(f"**Name:** {parsed.get('name', 'N/A')}")
            st.write(f"**Email:** {parsed.get('email', 'N/A')}")

            st.markdown("#### 🎓 Education")
            for edu in parsed.get("education", []):
                st.write(
                    f"- **{edu.get('degree', '')}** in {edu.get('field', '')} "
                    f"— {edu.get('institution', '')} ({edu.get('year', '')})"
                )

            st.markdown("#### 🔬 Research Interests")
            interests = parsed.get("research_interests", [])
            if interests:
                st.write(", ".join(interests))
            else:
                st.caption("None listed")

        with col2:
            st.markdown("#### 🛠️ Skills")
            skills = parsed.get("skills", [])
            if skills:
                # Display as tags
                st.write(" • ".join(skills))
            else:
                st.caption("None extracted")

            st.markdown("#### 💼 Experience")
            for exp in parsed.get("experience", []):
                st.write(
                    f"- **{exp.get('title', '')}** at {exp.get('company', '')} "
                    f"({exp.get('duration', '')})"
                )

            st.markdown("#### 📚 Publications")
            pubs = parsed.get("publications", [])
            if pubs:
                st.write(f"{len(pubs)} publication(s)")
                for pub in pubs[:5]:
                    st.caption(f"• {pub}" if isinstance(pub, str) else f"• {pub.get('title', '')}")
            else:
                st.caption("None listed")

        with st.expander("🔍 Full Parsed JSON"):
            st.json(parsed)

        # Navigation
        st.divider()
        persona = st.session_state.get("persona")

        if persona == PERSONA_STUDENT:
            st.info("Your CV is ready! Head to the **Student Dashboard** to find matching positions.")
            if st.button("Go to Student Dashboard →", type="primary"):
                st.switch_page("pages/02_Student_Dashboard.py")
        else:
            st.info("Your CV is ready! Head to the **Job Seeker Dashboard** to find matching jobs.")
            if st.button("Go to Job Seeker Dashboard →", type="primary"):
                st.switch_page("pages/03_Job_Seeker_Dashboard.py")

footer()
