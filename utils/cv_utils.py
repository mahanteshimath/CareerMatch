"""CV file handling — upload, staging, and text extraction."""

from __future__ import annotations

import time
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING
import xml.etree.ElementTree as ET
import zipfile

if TYPE_CHECKING:
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
    try:
        from PyPDF2 import PdfReader
    except ImportError as exc:
        raise ValueError("PyPDF2 is not installed. Please install dependencies.") from exc

    try:
        reader = PdfReader(uploaded_file)
    except Exception as exc:
        raise ValueError(f"Failed to read PDF: {exc}") from exc

    text_parts: list[str] = []
    for page in reader.pages:
        page_text = page.extract_text()
        if page_text:
            text_parts.append(page_text)
    return "\n".join(text_parts)


def extract_text_from_docx(uploaded_file) -> str:
    """Extract plain text from a DOCX file without external dependencies."""
    try:
        uploaded_file.seek(0)
        with zipfile.ZipFile(uploaded_file) as archive:
            xml_bytes = archive.read("word/document.xml")
    except Exception as exc:
        raise ValueError(f"Failed to read DOCX: {exc}") from exc

    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError as exc:
        raise ValueError(f"Failed to parse DOCX XML: {exc}") from exc

    namespaces = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
    text_nodes = root.findall(".//w:t", namespaces)
    text_parts = [(node.text or "").strip() for node in text_nodes if node.text]
    return "\n".join(part for part in text_parts if part)


def extract_text_from_cv(uploaded_file) -> str:
    """Extract text from a supported CV file format."""
    ext = Path(uploaded_file.name).suffix.lower()
    uploaded_file.seek(0)

    if ext == ".pdf":
        return extract_text_from_pdf(uploaded_file)
    if ext == ".docx":
        return extract_text_from_docx(uploaded_file)

    raise ValueError(f"Unsupported CV extension for text extraction: {ext}")


def stage_cv(session: Session, uploaded_file, user_id: int) -> str:
    """Upload CV to Snowflake stage. Returns the stage-relative file path."""
    timestamp = int(time.time())
    safe_name = Path(uploaded_file.name).stem.replace(" ", "_")
    ext = Path(uploaded_file.name).suffix
    stage_filename = f"{timestamp}_{user_id}_{safe_name}{ext}"

    tmp_path = ""
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as tmp:
            tmp.write(uploaded_file.getbuffer())
            tmp_path = tmp.name

        session.file.put(
            tmp_path,
            f"@IITJ.MH.CAREERMATCH_STAGE/{stage_filename}",
            auto_compress=False,
            overwrite=True,
        )
    except Exception as exc:
        raise RuntimeError(f"Failed to stage CV in Snowflake: {exc}") from exc
    finally:
        if tmp_path:
            Path(tmp_path).unlink(missing_ok=True)

    return stage_filename
