from __future__ import annotations

import io
import zipfile
from types import SimpleNamespace

from utils.cv_utils import extract_text_from_cv, validate_cv


class _UploadedFile(io.BytesIO):
    def __init__(self, name: str, content: bytes):
        super().__init__(content)
        self.name = name
        self.size = len(content)


def _build_minimal_docx(text: str) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, mode="w") as zf:
        zf.writestr(
            "word/document.xml",
            (
                "<?xml version='1.0' encoding='UTF-8'?>"
                "<w:document xmlns:w='http://schemas.openxmlformats.org/wordprocessingml/2006/main'>"
                f"<w:body><w:p><w:r><w:t>{text}</w:t></w:r></w:p></w:body>"
                "</w:document>"
            ),
        )
    return buffer.getvalue()


def test_validate_cv_rejects_unsupported_extension() -> None:
    uploaded = _UploadedFile("resume.txt", b"hello")
    error = validate_cv(uploaded)
    assert error is not None
    assert "Unsupported file type" in error


def test_extract_text_from_cv_docx() -> None:
    uploaded = _UploadedFile("resume.docx", _build_minimal_docx("Hello CareerMatch"))
    text = extract_text_from_cv(uploaded)
    assert "Hello CareerMatch" in text
