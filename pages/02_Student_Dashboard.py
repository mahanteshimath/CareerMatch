"""Student Dashboard — position filters, AI search, and semantic matching."""

from __future__ import annotations

import streamlit as st

from agents.orchestrator import orchestrate_position_search
from config.settings import APPLICATION_TYPES, CONTINENTS
from utils.matching import match_positions
from utils.ui_components import footer, page_header, require_auth, require_cv, require_snowflake_session, sidebar_user_info

page_header("Student Dashboard")
user_info = require_auth()
sidebar_user_info(user_info)
cv_data = require_cv()

session = require_snowflake_session()

# ── Filters ──────────────────────────────────────────────────────────────────
st.markdown("### 🔎 Find University Positions")

col_f1, col_f2, col_f3 = st.columns(3)

with col_f1:
    position_type = st.selectbox("Application Type", APPLICATION_TYPES)
with col_f2:
    continent = st.selectbox("Continent", ["All"] + CONTINENTS)
with col_f3:
    open_only = st.checkbox("Open deadlines only", value=True)

if continent == "All":
    continent = ""

# ── AI Deep Research ─────────────────────────────────────────────────────────
st.divider()

tab_ai, tab_db = st.tabs(["🤖 AI Deep Research", "📊 Database Match"])

with tab_ai:
    st.caption(
        "Uses Perplexity Sonar to research live university positions matching your CV."
    )
    if st.button("🔍 Search Positions with AI", type="primary", key="ai_search"):
        with st.spinner("AI is searching for positions... This may take 30-60 seconds."):
            result = orchestrate_position_search(
                session, cv_data, position_type, continent
            )
            if isinstance(result, dict) and "error" in result:
                st.error(f"Position search failed: {result['error']}")
            elif isinstance(result, list):
                st.session_state["ai_positions"] = result
                st.session_state["ai_positions_citations"] = []
            else:
                st.session_state["ai_positions"] = result.get("positions", [])
                st.session_state["ai_positions_citations"] = result.get("citations", [])

    if st.session_state.get("ai_positions"):
        results = st.session_state["ai_positions"]
        st.success(f"Found **{len(results)}** positions!")

        for i, pos in enumerate(results):
            with st.expander(
                f"🏫 {pos.get('title', 'Position')} — {pos.get('university', 'University')}",
                expanded=i == 0,
            ):
                col1, col2 = st.columns([2, 1])
                with col1:
                    st.write(f"**University:** {pos.get('university', 'N/A')}")
                    st.write(f"**Country:** {pos.get('country', 'N/A')} ({pos.get('continent', '')})")
                    st.write(f"**Type:** {pos.get('position_type', 'N/A')}")
                    st.write(f"**Deadline:** {pos.get('deadline', 'N/A')}")
                    if pos.get("description"):
                        st.markdown("**Description:**")
                        st.write(pos["description"][:500])

                with col2:
                    if pos.get("professor_name"):
                        st.write(f"**Professor:** {pos['professor_name']}")
                    if pos.get("professor_email"):
                        st.write(f"**Email:** {pos['professor_email']}")
                    if pos.get("source_url"):
                        st.link_button("🔗 View Source", pos["source_url"])
                    if pos.get("requirements"):
                        st.markdown("**Requirements:**")
                        st.write(pos["requirements"][:300])

                # Actions
                col_a, col_b = st.columns(2)
                with col_a:
                    if st.button(f"📝 Generate SOP", key=f"sop_{i}"):
                        st.session_state["selected_position"] = pos
                        st.session_state["draft_type"] = "SOP"
                        st.switch_page("pages/04_SOP_Generator.py")
                with col_b:
                    if st.button(f"✉️ Generate Email", key=f"email_{i}"):
                        st.session_state["selected_position"] = pos
                        st.session_state["draft_type"] = "Email"
                        st.switch_page("pages/04_SOP_Generator.py")

        # Citations
        citations = st.session_state.get("ai_positions_citations", [])
        if citations:
            with st.expander("📚 Sources", expanded=False):
                for idx, url in enumerate(citations, 1):
                    st.markdown(f"{idx}. {url}")

# ── Database semantic match ─────────────────────────────────────────────────
with tab_db:
    st.caption(
        "Matches your CV against positions already stored in the database using vector similarity."
    )
    if st.button("📊 Run Semantic Match", key="db_match"):
        cv_text = st.session_state.get("cv_text", "")
        if not cv_text:
            st.warning("CV text not found. Please re-upload your CV.")
        else:
            with st.spinner("Computing semantic similarity..."):
                filters = {
                    "position_type": position_type,
                    "continent": continent,
                    "open_only": open_only,
                }
                matches = match_positions(session, cv_text, filters, top_k=10)
                st.session_state["db_position_matches"] = matches

    if st.session_state.get("db_position_matches"):
        matches = st.session_state["db_position_matches"]
        if not matches:
            st.info("No matching positions found in the database. Try the AI Deep Research tab first.")
        else:
            st.success(f"Found **{len(matches)}** matching positions!")
            for i, match in enumerate(matches):
                score = match.get("SIMILARITY", 0)
                score_pct = f"{score * 100:.1f}%" if score else "N/A"

                with st.expander(
                    f"{'🟢' if score and score > 0.7 else '🟡' if score and score > 0.5 else '🔴'} "
                    f"{match.get('TITLE', 'Position')} — {match.get('UNIVERSITY', '')} "
                    f"(Match: {score_pct})",
                    expanded=i == 0,
                ):
                    col1, col2 = st.columns([2, 1])
                    with col1:
                        st.metric("Similarity Score", score_pct)
                        st.write(f"**University:** {match.get('UNIVERSITY', 'N/A')}")
                        st.write(f"**Country:** {match.get('COUNTRY', '')}")
                        st.write(f"**Type:** {match.get('POSITION_TYPE', 'N/A')}")
                        st.write(f"**Deadline:** {match.get('DEADLINE', 'N/A')}")
                    with col2:
                        if match.get("PROFESSOR_NAME"):
                            st.write(f"**Professor:** {match['PROFESSOR_NAME']}")
                        if match.get("SOURCE_URL"):
                            st.link_button("🔗 View Source", match["SOURCE_URL"])

                    col_a, col_b = st.columns(2)
                    with col_a:
                        if st.button(f"📝 Generate SOP", key=f"db_sop_{i}"):
                            st.session_state["selected_position"] = {
                                "title": match.get("TITLE", ""),
                                "university": match.get("UNIVERSITY", ""),
                                "description": match.get("DESCRIPTION", ""),
                                "requirements": match.get("REQUIREMENTS", ""),
                                "professor_name": match.get("PROFESSOR_NAME", ""),
                                "professor_email": match.get("PROFESSOR_EMAIL", ""),
                            }
                            st.session_state["draft_type"] = "SOP"
                            st.switch_page("pages/04_SOP_Generator.py")
                    with col_b:
                        if st.button(f"✉️ Generate Email", key=f"db_email_{i}"):
                            st.session_state["selected_position"] = {
                                "title": match.get("TITLE", ""),
                                "university": match.get("UNIVERSITY", ""),
                                "professor_name": match.get("PROFESSOR_NAME", ""),
                            }
                            st.session_state["draft_type"] = "Email"
                            st.switch_page("pages/04_SOP_Generator.py")

footer()
