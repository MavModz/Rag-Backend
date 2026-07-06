"""Chunking strategy.

Default is **context-aware**: split on paragraph + sentence boundaries so each
chunk holds coherent, whole sentences (never a sentence cut in half), with
sentence-level overlap for continuity. Runaway blocks with no sentence breaks are
hard-wrapped at word boundaries. Set ``chunk_strategy="fixed"`` for the legacy
character splitter. Pure function of its input — easy to unit test.
"""
from __future__ import annotations

import re

from langchain_text_splitters import RecursiveCharacterTextSplitter

from app.config import settings

# Sentence boundary: end punctuation followed by whitespace + a capital/quote/digit.
_SENTENCE = re.compile(r"(?<=[.!?])\s+(?=[\"'(\[]?[A-Z0-9])")
_PARAGRAPH = re.compile(r"\n\s*\n")


def chunk_text(
    text: str,
    chunk_size: int | None = None,
    chunk_overlap: int | None = None,
) -> list[str]:
    """Split text into chunks. Empty/whitespace input -> []."""
    if not text or not text.strip():
        return []
    size = chunk_size or settings.chunk_size
    overlap = chunk_overlap or settings.chunk_overlap
    if settings.chunk_strategy == "fixed":
        return _fixed_chunks(text, size, overlap)
    return _structure_chunks(text, size, overlap)


def _hard_wrap(text: str, size: int) -> list[str]:
    """Split a long, sentence-less block at word boundaries into <= size pieces."""
    pieces: list[str] = []
    cur: list[str] = []
    length = 0
    for word in text.split():
        if cur and length + len(word) + 1 > size:
            pieces.append(" ".join(cur))
            cur, length = [], 0
        cur.append(word)
        length += len(word) + 1
    if cur:
        pieces.append(" ".join(cur))
    return pieces


def _units(text: str, size: int) -> list[str]:
    """Flatten text into sentence-sized units (paragraph-aware), wrapping long ones."""
    units: list[str] = []
    for para in (p.strip() for p in _PARAGRAPH.split(text) if p.strip()):
        for sentence in (s.strip() for s in _SENTENCE.split(para) if s.strip()):
            if len(sentence) > size:
                units.extend(_hard_wrap(sentence, size))
            else:
                units.append(sentence)
    return units


def _structure_chunks(text: str, size: int, overlap: int) -> list[str]:
    chunks: list[str] = []
    cur: list[str] = []
    cur_len = 0
    for unit in _units(text, size):
        unit_len = len(unit) + 1
        if cur and cur_len + unit_len > size:
            chunks.append(" ".join(cur))
            # Carry trailing sentences (~overlap chars) into the next chunk.
            keep: list[str] = []
            keep_len = 0
            for prev in reversed(cur):
                if keep_len + len(prev) > overlap:
                    break
                keep.insert(0, prev)
                keep_len += len(prev) + 1
            cur, cur_len = keep, keep_len
        cur.append(unit)
        cur_len += unit_len
    if cur:
        chunks.append(" ".join(cur))
    return [c for c in chunks if c.strip()]


def _fixed_chunks(text: str, size: int, overlap: int) -> list[str]:
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=size, chunk_overlap=overlap, separators=["\n\n", "\n", ". ", " ", ""]
    )
    return [c for c in splitter.split_text(text) if c.strip()]
