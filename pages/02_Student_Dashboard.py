"""Student Dashboard — position filters, AI search, and semantic matching."""

from __future__ import annotations

import json

import streamlit as st

from agents.orchestrator import orchestrate_position_search
from config.settings import APPLICATION_TYPES, CONTINENTS, CORTEX_EMBED_MODEL
from utils.matching import match_positions
from utils.ui_components import (
    clear_session_prefixes,
    footer,
    page_header,
    require_auth,
    require_snowflake_session,
    sidebar_user_info,
)


def _coerce_parsed_json(value: object) -> dict | None:
    """Convert PARSED_JSON from Snowflake row into a Python dictionary."""
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, dict) else None
        except json.JSONDecodeError:
            return None
    return None


def _save_ai_positions_to_snowflake(
    session,
    user_id: int,
    cv_id: int,
    positions: list[dict],
) -> tuple[int, int]:
    """Persist AI position results and record them into CM_MATCHES history."""
    saved_positions = 0
    saved_matches = 0

    for pos in positions:
        title = str(pos.get("title", "")).strip()
        university = str(pos.get("university", "")).strip()
        if not title or not university:
            continue

        existing = session.sql(
            "SELECT POS_ID FROM IITJ.MH.CM_POSITIONS WHERE TITLE = ? AND UNIVERSITY = ?",
            params=[title, university],
        ).collect()

        if existing:
            pos_id = int(existing[0]["POS_ID"])
        else:
            session.sql(
                "INSERT INTO IITJ.MH.CM_POSITIONS "
                "(TITLE, UNIVERSITY, COUNTRY, CONTINENT, POSITION_TYPE, DEADLINE, "
                "DESCRIPTION, REQUIREMENTS, PROFESSOR_NAME, PROFESSOR_EMAIL, SOURCE_URL, EMBEDDING) "
                "SELECT ?, ?, ?, ?, ?, TRY_TO_DATE(?), ?, ?, ?, ?, ?, "
                "SNOWFLAKE.CORTEX.EMBED_TEXT_768(?, ?)",
                params=[
                    title,
                    university,
                    str(pos.get("country", "")),
                    str(pos.get("continent", "")),
                    str(pos.get("position_type", "")),
                    str(pos.get("deadline", "")),
                    str(pos.get("description", "")),
                    str(pos.get("requirements", "")),
                    str(pos.get("professor_name", "")),
                    str(pos.get("professor_email", "")),
                    str(pos.get("source_url", "")),
                    CORTEX_EMBED_MODEL,
                    (
                        f"{title}\n"
                        f"{pos.get('description', '')}\n"
                        f"{pos.get('requirements', '')}"
                    )[:8000],
                ],
            ).collect()

            lookup = session.sql(
                "SELECT POS_ID FROM IITJ.MH.CM_POSITIONS WHERE TITLE = ? AND UNIVERSITY = ?",
                params=[title, university],
            ).collect()
            if not lookup:
                continue
            pos_id = int(lookup[0]["POS_ID"])
            saved_positions += 1

        inserted = session.sql(
            "INSERT INTO IITJ.MH.CM_MATCHES "
            "(USER_ID, CV_ID, TARGET_TYPE, TARGET_ID, SIMILARITY_SCORE, MISSING_SKILLS) "
            "SELECT ?, ?, 'position', ?, NULL, NULL "
            "WHERE NOT EXISTS ("
            "  SELECT 1 FROM IITJ.MH.CM_MATCHES "
            "  WHERE USER_ID = ? AND CV_ID = ? AND TARGET_TYPE = 'position' AND TARGET_ID = ?"
            ")",
            params=[user_id, cv_id, pos_id, user_id, cv_id, pos_id],
        ).collect()
        if inserted:
            saved_matches += 1

    return saved_positions, saved_matches

page_header("Student Dashboard")
user_info = require_auth()
sidebar_user_info(user_info)

session = require_snowflake_session()
user_id = st.session_state.get("user_id")

stored_cv_options: list[tuple[str, dict, int | None]] = []

if user_id:
    cv_rows = session.sql(
        "SELECT CV_ID, CV_FILE_PATH, PARSED_JSON, UPLOADED_AT "
        "FROM IITJ.MH.CM_CVS WHERE USER_ID = ? "
        "ORDER BY UPLOADED_AT DESC",
        params=[user_id],
    ).collect()
    for row in cv_rows:
        parsed = _coerce_parsed_json(row["PARSED_JSON"])
        if parsed:
            label = f"{row['CV_FILE_PATH']} ({row['UPLOADED_AT']})"
            stored_cv_options.append((label, parsed, int(row["CV_ID"])))

cv_data = st.session_state.get("parsed_cv") if isinstance(st.session_state.get("parsed_cv"), dict) else None
selected_cv_id = st.session_state.get("selected_cv_id")

if cv_data:
    stored_cv_options.insert(0, ("Current session CV", cv_data, selected_cv_id))

if stored_cv_options:
    cv_labels = [item[0] for item in stored_cv_options]
    selected_label = st.selectbox("CV source for position search", cv_labels, key="position_search_cv_source")
    selected_entry = next(item for item in stored_cv_options if item[0] == selected_label)
    cv_data = selected_entry[1]
    selected_cv_id = selected_entry[2]
    st.session_state["parsed_cv"] = cv_data
    st.session_state["selected_cv_id"] = selected_cv_id
else:
    cv_data = None
    st.warning("No parsed CV available. Upload and parse a CV once to reuse it for future searches.")

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
        if not cv_data:
            st.warning("Please upload/parse a CV first, or choose one from your stored CVs.")
            st.stop()
        clear_session_prefixes(("skill_analysis_", "db_skill_analysis_"))
        st.session_state.pop("ai_positions", None)
        st.session_state.pop("ai_positions_citations", None)
        with st.spinner("AI is searching for positions... This may take 30-60 seconds."):
            result = orchestrate_position_search(
                session, cv_data, position_type, continent
            )
            if isinstance(result, dict) and "error" in result:
                st.error(f"Position search failed: {result['error']}")
            elif isinstance(result, list):
                st.session_state["ai_positions"] = result
                st.session_state["ai_positions_citations"] = []
                if not result:
                    st.warning("No positions were returned from cache. Retrying should fetch fresh results.")
            else:
                st.session_state["ai_positions"] = result.get("positions", [])
                st.session_state["ai_positions_citations"] = result.get("citations", [])
                if not st.session_state["ai_positions"]:
                    st.info("No matching positions found right now. Try again or adjust filters.")

    if st.session_state.get("ai_positions"):
        results = st.session_state["ai_positions"]
        st.success(f"Found **{len(results)}** positions!")

        if user_id:
            if st.button("💾 Save AI Positions to Snowflake", key="save_ai_positions_to_db"):
                if not selected_cv_id:
                    st.warning(
                        "Please select a previously uploaded CV from the dropdown to save match history. "
                        "Current session CV may not yet be linked to a CV_ID."
                    )
                else:
                    with st.spinner("Saving positions and match history to Snowflake..."):
                        try:
                            saved_positions, saved_matches = _save_ai_positions_to_snowflake(
                                session,
                                user_id,
                                selected_cv_id,
                                results,
                            )
                            st.success(
                                "Saved to Snowflake. "
                                f"New positions inserted: {saved_positions}, new matches recorded: {saved_matches}."
                            )
                        except Exception as exc:
                            st.error(f"Failed to save AI positions: {exc}")
        else:
            st.info("User ID not found. Please sign in again to save positions.")

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
        clear_session_prefixes(("skill_analysis_", "db_skill_analysis_"))
        st.session_state.pop("db_position_matches", None)
        cv_text = st.session_state.get("cv_text", "")
        if not cv_text:
            st.warning(
                "CV text not found in current session. Uploading again is not required for AI search, "
                "but semantic match currently needs in-session CV text."
            )
        else:
            with st.spinner("Computing semantic similarity..."):
                filters = {
                    "position_type": position_type,
                    "continent": continent,
                    "open_only": open_only,
                }
                try:
                    matches = match_positions(session, cv_text, filters, top_k=10)
                    st.session_state["db_position_matches"] = matches
                except Exception as exc:
                    st.error(f"Semantic match failed: {exc}")

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
