# CLAUDE.md

Operational and development runbook for CareerMatch.

## Goals
- Keep the app stable for 1000+ daily active users on Streamlit Cloud.
- Prioritize reliability, graceful degradation, and debuggability.
- Avoid architecture changes requiring external queue/worker infrastructure in this phase.

## Local Development
- Install dependencies: `pip install -r requirements.txt`
- Run app: `streamlit run Home.py`
- Lint: `ruff check .`
- Tests: `pytest tests/ -v`

## Required Secrets
- Snowflake connection under Streamlit connections/secrets.
- Perplexity API key in one of:
  - `st.secrets["api_keys"]["perplexity"]`
  - `st.secrets["PERPLEXITY_API_KEY"]`
  - env `PERPLEXITY_API_KEY`

If the key is missing, Home page will warn and AI features should be treated as unavailable.

## Runtime Guardrails
- Do not let DB persistence failures block user-visible AI results.
- Always return actionable error messages for external API failures.
- Keep transient session state bounded by clearing stale analysis keys on new searches.
- Preserve cache table hygiene by deleting expired rows.

## Snowflake Notes
- Tables/stage are auto-created at startup via `utils/snowflake_utils.py`.
- Performance objects are applied at startup:
  - Search optimization on cache lookup columns.
  - Search optimization on common position/job filter columns.
- Expired rows in `CM_AGENT_CACHE` are removed at startup cleanup.

## Incident Response
1. Check whether Perplexity API key is configured and valid.
2. Verify Snowflake connectivity from Home page startup.
3. Inspect logs for:
   - `cache_lookup_failed`
   - `cache_store_failed`
   - `position_upsert_failed`
   - `job_upsert_failed`
   - `perplexity_retryable_status_exhausted`
4. If Perplexity is degraded/rate-limited, retry later and communicate degraded mode.

## Rollback Approach
- Keep changes small and revert by file if needed.
- Prioritize rollback of startup/bootstrap DDL changes only if they block app boot.
- Do not rollback failure-isolation improvements unless they cause functional regressions.

## Daily Health Checks
- Verify app boots and login works.
- Run one Student AI search and one Job AI search.
- Run one semantic match in each dashboard.
- Confirm cache cleanup continues to remove expired entries.

## Change Management
- Require lint + test pass before merge.
- Add tests when adding retry logic, parsing logic, or session-state behavior.
- Keep public behavior stable while improving reliability.
