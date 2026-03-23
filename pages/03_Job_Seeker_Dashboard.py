"""Job Seeker Dashboard — job search, semantic matching, and skill gap analysis."""

from __future__ import annotations

import streamlit as st

from agents.orchestrator import orchestrate_job_search, orchestrate_skill_analysis
from utils.matching import match_jobs
from utils.ui_components import (
    clear_session_prefixes,
    footer,
    page_header,
    require_auth,
    require_cv,
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


# ── Page setup ───────────────────────────────────────────────────────────────
page_header("Job Seeker Dashboard")
user_info = require_auth()
sidebar_user_info(user_info)
cv_data = require_cv()

session = require_snowflake_session()

# ── Search ───────────────────────────────────────────────────────────────────
st.markdown("### 🔎 Find Matching Jobs")

tab_ai, tab_db = st.tabs(["🤖 AI Job Research", "📊 Database Match"])

# ── AI Job Research ──────────────────────────────────────────────────────────
with tab_ai:
    st.caption(
        "Uses Perplexity Sonar to research real job listings matching your profile."
    )
    if st.button("🔍 Search Jobs with AI", type="primary", key="ai_job_search"):
        clear_session_prefixes(("skill_analysis_", "db_skill_analysis_"))
        st.session_state.pop("ai_jobs", None)
        st.session_state.pop("ai_jobs_citations", None)
        with st.spinner("AI is searching the job market... This may take 30-60 seconds."):
            result = orchestrate_job_search(session, cv_data)
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
            st.warning("CV text not found. Please re-upload your CV.")
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
