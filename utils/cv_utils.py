"""CV file handling — upload, staging, and text extraction."""

from __future__ import annotations

import time
import tempfile
from pathlib import Path

import streamlit as st
from PyPDF2 import PdfReader
from snowflake.snowpark import Session

from config.settings import ALLOWED_CV_EXTENSIONS, MAX_CV_SIZE_MB


def validate_cv(uploaded_file) -> str | None:
    """Validate uploaded CV file. Returns error message or None if valid."""
    if uploaded_file is None:
        return "No file uploaded."

    ext = Path(uploaded_file.name).suffix.lower()
    if ext not in ALLOWED_CV_EXTENSIONS:
        return f"Unsupported file type: {ext}. Allowed: {ALLOWED_CV_EXTENSIONS}"

    size_mb = uploaded_file.size / (1024 * 1024)
    if size_mb > MAX_CV_SIZE_MB:
        return f"File too large ({size_mb:.1f} MB). Maximum: {MAX_CV_SIZE_MB} MB."

    return None


def extract_text_from_pdf(uploaded_file) -> str:
    """Extract raw text from a PDF file."""
    reader = PdfReader(uploaded_file)
    text_parts: list[str] = []
    for page in reader.pages:
        page_text = page.extract_text()
        if page_text:
            text_parts.append(page_text)
    return "\n".join(text_parts)


def stage_cv(session: Session, uploaded_file, user_id: int) -> str:
    """Upload CV to Snowflake stage. Returns the stage-relative file path."""
    timestamp = int(time.time())
    safe_name = Path(uploaded_file.name).stem.replace(" ", "_")
    ext = Path(uploaded_file.name).suffix
    stage_filename = f"{timestamp}_{user_id}_{safe_name}{ext}"

    with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as tmp:
        tmp.write(uploaded_file.getbuffer())
        tmp_path = tmp.name

    session.file.put(
        tmp_path,
        f"@IITJ.MH.CAREERMATCH_STAGE/{stage_filename}",
        auto_compress=False,
        overwrite=True,
    )

    Path(tmp_path).unlink(missing_ok=True)
    return stage_filename
