# CareerMatch — Project Guidelines

## Overview

CareerMatch is a SaaS AI-powered CV-to-opportunity matching platform built with **Streamlit + Snowflake + LangChain + Perplexity Sonar**. Two personas:

- **Student**: Upload CV → filter (Masters/PhD/Postdoc, continent, open deadlines) → match university positions → generate SOP/email drafts
- **Job Seeker**: Upload CV → NLP extraction → semantic match against job descriptions → similarity scores → highlight missing skills

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Frontend | Streamlit (multi-page app) |
| Backend DB | Snowflake (`IITJ.MH` schema) |
| Auth | Google Sign-in via `streamlit-google-auth` |
| AI/NLP | Perplexity Sonar API via LangChain multi-agent |
| Embeddings | Snowflake Cortex `EMBED_TEXT` for semantic matching |
| CV Parsing | LangChain agent + Perplexity for structured extraction |

## Architecture

```
Home.py                          # Entry point: Google auth, Snowflake init, persona routing
pages/
  01_Upload_CV.py                # CV upload + AI parsing
  02_Student_Dashboard.py        # Student: position filters + matching
  03_Job_Seeker_Dashboard.py     # Job Seeker: job matching + skill gap
  04_SOP_Generator.py            # Student: SOP/email draft from position + CV
  05_Profile.py                  # User profile management
agents/
  cv_parser.py                   # LangChain agent: extract structured data from CV
  position_researcher.py         # LangChain agent: search university positions via Perplexity
  job_researcher.py              # LangChain agent: search job listings via Perplexity
  sop_writer.py                  # LangChain agent: generate SOP/email drafts
  skill_analyzer.py              # LangChain agent: identify skill gaps
  orchestrator.py                # Multi-agent orchestration
utils/
  snowflake_utils.py             # Connection, session, schema init
  auth.py                        # Google OAuth helpers
  cv_utils.py                    # CV file handling, staging
  matching.py                    # Similarity scoring, ranking
  ui_components.py               # Shared Streamlit UI widgets
config/
  settings.py                    # App configuration constants
  schema.sql                     # Snowflake DDL (reference only; auto-created at runtime)
```

## Code Style

- **Python 3.11+**, type hints on all function signatures
- Follow PEP 8; use `ruff` for linting
- Streamlit pages: prefix with numeric order (`01_`, `02_`, etc.)
- Use `st.cache_data` / `st.cache_resource` for expensive operations
- Never hardcode credentials — use `.streamlit/secrets.toml` (gitignored) or env vars

## Build and Test

```bash
# Install
pip install -r requirements.txt

# Run locally
streamlit run Home.py

# Lint
ruff check .

# Test
pytest tests/ -v
```

## Snowflake Conventions

- All tables auto-created on first run (like reference repos)
- Schema: `IITJ.MH` — all objects live here
- CVs stored in Snowflake Stage (`CAREERMATCH_STAGE`, SSE-encrypted)
- Use `snowflake-snowpark-python` for Snowflake interaction
- Connection via `st.connection("snowflake")` with `secrets.toml` fallback

## LangChain Agent Conventions

- Agents live in `agents/` directory, one file per agent
- Use `ChatPerplexity` (model: `sonar`) as the LLM
- Each agent has a clear system prompt defining its role
- Orchestrator chains agents; never call Perplexity directly from pages
- Cache agent results in Snowflake to avoid redundant API calls

## Security

- **NEVER** commit `.streamlit/secrets.toml` — it's in `.gitignore`
- Google OAuth client secrets go in secrets.toml, not source code
- Validate all user input before passing to SQL or agents
- Use parameterized queries — never string-interpolate SQL
- Sanitize uploaded file names (timestamp prefix, like reference repos)

## Key Patterns from Reference Repos

- **Auto-schema migration**: Tables/stages created automatically on first run (`utils/snowflake_utils.py`)
- **Multi-page Streamlit**: `Home.py` as entry + `pages/` directory
- **Secrets management**: `.streamlit/secrets.toml` locally, Streamlit Cloud secrets in production
- **File staging**: Upload to Snowflake stage with Unix timestamp prefix to prevent collisions
