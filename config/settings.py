"""App configuration constants."""

import os

# Snowflake
SNOWFLAKE_DATABASE = "iitj"
SNOWFLAKE_SCHEMA = "mh"
SNOWFLAKE_STAGE = "CAREERMATCH_STAGE"

# Personas
PERSONA_STUDENT = "Student"
PERSONA_JOB_SEEKER = "Job Seeker"
PERSONAS = [PERSONA_STUDENT, PERSONA_JOB_SEEKER]

# Student filters
APPLICATION_TYPES = ["Masters", "PhD", "Postdoc"]
CONTINENTS = ["USA", "Europe/UK", "India", "Asia", "Australia", "Canada"]

# Perplexity
PERPLEXITY_MODEL = os.getenv("PERPLEXITY_MODEL", "sonar")
PERPLEXITY_API_URL = os.getenv(
	"PERPLEXITY_API_URL",
	"https://api.perplexity.ai/chat/completions",
)

# Embedding
CORTEX_EMBED_MODEL = "e5-base-v2"

# File upload
ALLOWED_CV_EXTENSIONS = [".pdf", ".docx"]
MAX_CV_SIZE_MB = 10

# App metadata
APP_NAME = "CareerMatch"
APP_ICON = "🎯"
APP_DESCRIPTION = "AI-powered CV-to-opportunity matching platform"
