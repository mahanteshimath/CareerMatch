"""Job Seeker Dashboard — job search, semantic matching, and skill gap analysis."""

from __future__ import annotations

import json

import streamlit as st

from agents.orchestrator import orchestrate_job_search, orchestrate_skill_analysis
from config.settings import CORTEX_EMBED_MODEL
from utils.matching import match_jobs
from utils.ui_components import (
    clear_session_prefixes,
    footer,
    page_header,
    require_auth,
    require_snowflake_session,
    sidebar_user_info,
)


# ── Helper ───────────────────────────────────────────────────────────────────
def _render_skill_analysis(analysis: dict) -> None:
    """Render a skill gap analysis result."""
    st.divider()
    st.markdown("#### 📊 Skill Gap Analysis")

    match_pct = analysis.get("match_percentage", 0)
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Match", f"{match_pct}%")
    with col2:
        st.metric("Matching Skills", len(analysis.get("matching_skills", [])))
    with col3:
        st.metric("Missing Skills", len(analysis.get("missing_skills", [])))

    col_a, col_b = st.columns(2)
    with col_a:
        st.markdown("**✅ Matching Skills:**")
        for s in analysis.get("matching_skills", []):
            st.write(f"• {s}")
        if analysis.get("transferable_skills"):
            st.markdown("**🔄 Transferable Skills:**")
            for s in analysis["transferable_skills"]:
                st.write(f"• {s}")
    with col_b:
        st.markdown("**❌ Missing Skills:**")
        for s in analysis.get("missing_skills", []):
            st.write(f"• {s}")

    if analysis.get("recommendations"):
        st.markdown("**💡 Recommendations:**")
        for rec in analysis["recommendations"]:
            st.info(rec)

    if analysis.get("overall_assessment"):
        st.markdown("**📝 Overall Assessment:**")
        st.write(analysis["overall_assessment"])


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


def _save_ai_jobs_to_snowflake(
    session,
    user_id: int,
    cv_id: int,
    jobs: list[dict],
) -> tuple[int, int]:
    """Persist AI job results and record them into CM_MATCHES history."""
    saved_jobs = 0
    saved_matches = 0

    for job in jobs:
        title = str(job.get("title", "")).strip()
        company = str(job.get("company", "")).strip()
        if not title or not company:
            continue

        existing = session.sql(
            "SELECT JOB_ID FROM IITJ.MH.CM_JOBS WHERE TITLE = ? AND COMPANY = ?",
            params=[title, company],
        ).collect()

        if existing:
            job_id = int(existing[0]["JOB_ID"])
        else:
            required_skills = job.get("required_skills", [])
            if isinstance(required_skills, list):
                required_skills = ", ".join(required_skills)
            required_skills = str(required_skills)

            session.sql(
                "INSERT INTO IITJ.MH.CM_JOBS "
                "(TITLE, COMPANY, LOCATION, DESCRIPTION, REQUIRED_SKILLS, "
                "EXPERIENCE_LEVEL, SALARY_RANGE, SOURCE_URL, EMBEDDING) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, SNOWFLAKE.CORTEX.EMBED_TEXT_768(?, ?))",
                params=[
                    title,
                    company,
                    str(job.get("location", "")),
                    str(job.get("description", "")),
                    required_skills,
                    str(job.get("experience_level", "")),
                    str(job.get("salary_range", "")),
                    str(job.get("source_url", "")),
                    CORTEX_EMBED_MODEL,
                    (
                        f"{title}\n"
                        f"{job.get('description', '')}\n"
                        f"Required skills: {required_skills}"
                    )[:8000],
                ],
            ).collect()

            lookup = session.sql(
                "SELECT JOB_ID FROM IITJ.MH.CM_JOBS WHERE TITLE = ? AND COMPANY = ?",
                params=[title, company],
            ).collect()
            if not lookup:
                continue
            job_id = int(lookup[0]["JOB_ID"])
            saved_jobs += 1

        inserted = session.sql(
            "INSERT INTO IITJ.MH.CM_MATCHES "
            "(USER_ID, CV_ID, TARGET_TYPE, TARGET_ID, SIMILARITY_SCORE, MISSING_SKILLS) "
            "SELECT ?, ?, 'job', ?, NULL, NULL "
            "WHERE NOT EXISTS ("
            "  SELECT 1 FROM IITJ.MH.CM_MATCHES "
            "  WHERE USER_ID = ? AND CV_ID = ? AND TARGET_TYPE = 'job' AND TARGET_ID = ?"
            ")",
            params=[user_id, cv_id, job_id, user_id, cv_id, job_id],
        ).collect()
        if inserted:
            saved_matches += 1

    return saved_jobs, saved_matches


# ── Page setup ───────────────────────────────────────────────────────────────
page_header("Job Seeker Dashboard")
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
    selected_label = st.selectbox("CV source for job search", cv_labels, key="job_search_cv_source")
    selected_entry = next(item for item in stored_cv_options if item[0] == selected_label)
    cv_data = selected_entry[1]
    selected_cv_id = selected_entry[2]
    st.session_state["parsed_cv"] = cv_data
    st.session_state["selected_cv_id"] = selected_cv_id
else:
    cv_data = None
    st.warning("No parsed CV available. Upload and parse a CV once to reuse it for future searches.")

# ── Search ───────────────────────────────────────────────────────────────────
st.markdown("### 🔎 Find Matching Jobs")

tab_ai, tab_db = st.tabs(["🤖 AI Job Research", "📊 Database Match"])

# ── AI Job Research ──────────────────────────────────────────────────────────
with tab_ai:
    st.caption(
        "Uses Perplexity Sonar to research real job listings matching your profile."
    )
    custom_instructions = st.text_area(
        "Optional custom instructions",
        placeholder="Example: Search all jobs in Bengaluru only.",
        height=90,
        key="job_search_custom_instructions",
        help=(
            "Use this to constrain search scope, such as location, role type, "
            "or work mode."
        ),
    )

    if st.button("🔍 Search Jobs with AI", type="primary", key="ai_job_search"):
        if not cv_data:
            st.warning("Please upload/parse a CV first, or choose one from your stored CVs.")
            st.stop()
        clear_session_prefixes(("skill_analysis_", "db_skill_analysis_"))
        st.session_state.pop("ai_jobs", None)
        st.session_state.pop("ai_jobs_citations", None)
        with st.spinner("AI is searching the job market... This may take 30-60 seconds."):
            result = orchestrate_job_search(
                session,
                cv_data,
                custom_instructions=custom_instructions,
            )
            if isinstance(result, dict) and "error" in result:
                st.error(f"Job search failed: {result['error']}")
            elif isinstance(result, list):
                st.session_state["ai_jobs"] = result
                st.session_state["ai_jobs_citations"] = []
                if not result:
                    st.warning("No jobs were returned from cache. Retrying should fetch fresh results.")
            else:
                st.session_state["ai_jobs"] = result.get("jobs", [])
                st.session_state["ai_jobs_citations"] = result.get("citations", [])
                if not st.session_state["ai_jobs"]:
                    st.info("No matching jobs found right now. Try again or refine your CV/profile details.")

    if st.session_state.get("ai_jobs"):
        results = st.session_state["ai_jobs"]
        st.success(f"Found **{len(results)}** job opportunities!")

        if user_id:
            if st.button("💾 Save AI Jobs to Snowflake", key="save_ai_jobs_to_db"):
                if not selected_cv_id:
                    st.warning(
                        "Please select a previously uploaded CV from the dropdown to save match history. "
                        "Current session CV may not yet be linked to a CV_ID."
                    )
                else:
                    with st.spinner("Saving jobs and match history to Snowflake..."):
                        try:
                            saved_jobs, saved_matches = _save_ai_jobs_to_snowflake(
                                session,
                                user_id,
                                selected_cv_id,
                                results,
                            )
                            st.success(
                                "Saved to Snowflake. "
                                f"New jobs inserted: {saved_jobs}, new matches recorded: {saved_matches}."
                            )
                        except Exception as exc:
                            st.error(f"Failed to save AI jobs: {exc}")
        else:
            st.info("User ID not found. Please sign in again to save jobs.")

        for i, job in enumerate(results):
            with st.expander(
                f"💼 {job.get('title', 'Job')} — {job.get('company', 'Company')}",
                expanded=i == 0,
            ):
                col1, col2 = st.columns([2, 1])
                with col1:
                    st.write(f"**Company:** {job.get('company', 'N/A')}")
                    st.write(f"**Location:** {job.get('location', 'N/A')}")
                    st.write(f"**Experience Level:** {job.get('experience_level', 'N/A')}")
                    if job.get("salary_range"):
                        st.write(f"**Salary:** {job['salary_range']}")
                    if job.get("description"):
                        st.markdown("**Description:**")
                        st.write(job["description"][:500])

                with col2:
                    required = job.get("required_skills", [])
                    if isinstance(required, str):
                        required = [s.strip() for s in required.split(",")]
                    if required:
                        st.markdown("**Required Skills:**")
                        for skill in required:
                            st.write(f"• {skill}")
                    if job.get("source_url"):
                        st.link_button("🔗 Apply / View", job["source_url"])

                # Skill gap analysis
                if st.button(f"🔬 Analyze Skill Gap", key=f"skill_gap_{i}"):
                    req_skills = job.get("required_skills", [])
                    if isinstance(req_skills, str):
                        req_skills = [s.strip() for s in req_skills.split(",")]

                    with st.spinner("Analyzing skill gap..."):
                        analysis = orchestrate_skill_analysis(
                            session,
                            cv_data,
                            job.get("description", ""),
                            req_skills,
                        )
                        if isinstance(analysis, dict) and "error" in analysis:
                            st.error(f"Skill analysis failed: {analysis['error']}")
                        else:
                            st.session_state[f"skill_analysis_{i}"] = analysis

                if st.session_state.get(f"skill_analysis_{i}"):
                    analysis = st.session_state[f"skill_analysis_{i}"]
                    _render_skill_analysis(analysis)

        # Citations
        citations = st.session_state.get("ai_jobs_citations", [])
        if citations:
            with st.expander("📚 Sources", expanded=False):
                for idx, url in enumerate(citations, 1):
                    st.markdown(f"{idx}. {url}")

# ── Database semantic match ─────────────────────────────────────────────────
with tab_db:
    st.caption(
        "Matches your CV against jobs already stored in the database using vector similarity."
    )
    if st.button("📊 Run Semantic Match", key="db_job_match"):
        clear_session_prefixes(("skill_analysis_", "db_skill_analysis_"))
        st.session_state.pop("db_job_matches", None)
        cv_text = st.session_state.get("cv_text", "")
        if not cv_text:
            st.warning(
                "CV text not found in current session. Uploading again is not required for AI search, "
                "but semantic match currently needs in-session CV text."
            )
        else:
            with st.spinner("Computing semantic similarity..."):
                try:
                    matches = match_jobs(session, cv_text, top_k=10)
                    st.session_state["db_job_matches"] = matches
                except Exception as exc:
                    st.error(f"Semantic match failed: {exc}")

    if st.session_state.get("db_job_matches"):
        matches = st.session_state["db_job_matches"]
        if not matches:
            st.info("No matching jobs found in the database. Try the AI Job Research tab first.")
        else:
            st.success(f"Found **{len(matches)}** matching jobs!")
            for i, match in enumerate(matches):
                score = match.get("SIMILARITY", 0)
                score_pct = f"{score * 100:.1f}%" if score else "N/A"

                with st.expander(
                    f"{'🟢' if score and score > 0.7 else '🟡' if score and score > 0.5 else '🔴'} "
                    f"{match.get('TITLE', 'Job')} — {match.get('COMPANY', '')} "
                    f"(Match: {score_pct})",
                    expanded=i == 0,
                ):
                    col1, col2 = st.columns([2, 1])
                    with col1:
                        st.metric("Similarity Score", score_pct)
                        st.write(f"**Company:** {match.get('COMPANY', 'N/A')}")
                        st.write(f"**Location:** {match.get('LOCATION', '')}")
                        st.write(f"**Experience:** {match.get('EXPERIENCE_LEVEL', 'N/A')}")
                        if match.get("SALARY_RANGE"):
                            st.write(f"**Salary:** {match['SALARY_RANGE']}")
                    with col2:
                        req = match.get("REQUIRED_SKILLS", "")
                        if req:
                            st.markdown("**Required Skills:**")
                            for s in req.split(","):
                                st.write(f"• {s.strip()}")
                        if match.get("SOURCE_URL"):
                            st.link_button("🔗 Apply / View", match["SOURCE_URL"])

                    # Skill gap
                    if st.button(f"🔬 Analyze Skill Gap", key=f"db_skill_gap_{i}"):
                        req_skills = [
                            s.strip()
                            for s in match.get("REQUIRED_SKILLS", "").split(",")
                            if s.strip()
                        ]
                        with st.spinner("Analyzing skill gap..."):
                            analysis = orchestrate_skill_analysis(
                                session,
                                cv_data,
                                match.get("DESCRIPTION", ""),
                                req_skills,
                            )
                            if isinstance(analysis, dict) and "error" in analysis:
                                st.error(f"Skill analysis failed: {analysis['error']}")
                            else:
                                st.session_state[f"db_skill_analysis_{i}"] = analysis

                    if st.session_state.get(f"db_skill_analysis_{i}"):
                        analysis = st.session_state[f"db_skill_analysis_{i}"]
                        _render_skill_analysis(analysis)

footer()
