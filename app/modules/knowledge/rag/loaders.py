"""Document loaders: extract raw text from PDF and DOCX files.

Each loader returns the full document text as a single string. Chunking is a
separate concern (see chunker.py).
"""
from __future__ import annotations

import re
from pathlib import Path

import docx
from pypdf import PdfReader

from app.platform.observability.logging import get_logger

logger = get_logger(__name__)


def _normalize(text: str) -> str:
    """Clean up PDF/DOCX extraction artifacts (stray double-spaces, blank runs)."""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]{2,}", " ", text)   # collapse runs of spaces/tabs
    text = re.sub(r" *\n *", "\n", text)      # trim spaces around newlines
    text = re.sub(r"\n{3,}", "\n\n", text)   # cap blank-line runs
    return text.strip()


class UnsupportedFileType(ValueError):
    pass


def load_pdf(path: str | Path) -> str:
    reader = PdfReader(str(path))
    pages = [page.extract_text() or "" for page in reader.pages]
    return "\n\n".join(pages)


def load_docx(path: str | Path) -> str:
    document = docx.Document(str(path))
    paragraphs = [p.text for p in document.paragraphs if p.text and p.text.strip()]
    return "\n".join(paragraphs)


def load_document(path: str | Path) -> str:
    """Dispatch by file extension. Returns extracted text."""
    suffix = Path(path).suffix.lower()
    if suffix == ".pdf":
        text = load_pdf(path)
    elif suffix in (".docx", ".doc"):
        text = load_docx(path)
    else:
        raise UnsupportedFileType(f"Unsupported file type: {suffix!r}")

    text = _normalize(text)
    logger.info("Loaded %s (%d chars)", Path(path).name, len(text))
    return text
