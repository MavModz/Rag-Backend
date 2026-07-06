"""Context building: assemble retrieved KB chunks and prior chat turns into the
text blocks that get injected into the generation prompt.

Pure formatting — no I/O — so it is trivial to unit test.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from app.modules.knowledge.rag.vector_store import RetrievedChunk
from app.platform.connectors.base import ChatTurn

_IMAGE_LINE = re.compile(r"^\[Image \([^)]+\):.*\]$", re.MULTILINE)
_STEP_SPLIT = re.compile(r"(?=(?:^|\n)\s*Step\s+\d+)", re.IGNORECASE)
_NUMBERED_SPLIT = re.compile(r"(?=(?:^|\n)\s*\d+\.\s+)")
_STEP_TITLE = re.compile(r"^Step\s+(\d+)\s*[:\-]?\s*(.*)$", re.IGNORECASE | re.DOTALL)
_NUMBERED_TITLE = re.compile(r"^(\d+)\.\s+(.*)$", re.DOTALL)


@dataclass
class _ProcedureStep:
    title: str
    action: str = ""
    images: list[str] = field(default_factory=list)


def build_kb_context(chunks: list[RetrievedChunk], *, procedural: bool = False) -> str:
    """Render retrieved chunks for the generation prompt."""
    if not chunks:
        return "No relevant knowledge base context was found."
    if procedural:
        focused = _build_procedural_context(chunks)
        if focused:
            return focused
    lines = []
    for i, chunk in enumerate(chunks, start=1):
        lines.append(f"[{i}] (source: {chunk.source})\n{chunk.text.strip()}")
    return "\n\n".join(lines)


def _build_procedural_context(chunks: list[RetrievedChunk]) -> str:
    merged = "\n\n".join(chunk.text.strip() for chunk in chunks if chunk.text.strip())
    steps = _parse_steps_from_text(merged)
    if not steps:
        return _truncate_chunks(chunks, max_chunks=3, max_chars=500)

    source = chunks[0].source if chunks else "knowledge base"
    lines = [f"Procedure extracted from: {source}"]
    for index, step in enumerate(steps, start=1):
        lines.append(f"{index}. {step.title}")
        if step.action:
            lines.append(f"   Action: {step.action}")
        for image in step.images[:1]:
            lines.append(f"   Visual: {image}")
    return "\n".join(lines)


def _parse_steps_from_text(text: str) -> list[_ProcedureStep]:
    steps = _split_steps(text, _STEP_SPLIT, _STEP_TITLE)
    if steps:
        return steps
    return _split_steps(text, _NUMBERED_SPLIT, _NUMBERED_TITLE)


def _split_steps(text: str, splitter: re.Pattern[str], title_re: re.Pattern[str]) -> list[_ProcedureStep]:
    parts = [part.strip() for part in splitter.split(text) if part.strip()]
    steps: list[_ProcedureStep] = []
    for part in parts:
        match = title_re.match(part)
        if not match:
            continue
        body = match.group(2).strip()
        lines = [line.strip() for line in body.splitlines() if line.strip()]
        title = lines[0].rstrip(".") if lines else f"Step {match.group(1)}"
        images = [line for line in lines if _IMAGE_LINE.match(line)]
        action = ""
        for line in lines[1:]:
            if _IMAGE_LINE.match(line):
                continue
            if len(line) >= 12:
                action = _trim_action(line)
                break
        steps.append(_ProcedureStep(title=title, action=action, images=images))
    return steps[:8]


def _trim_action(line: str, limit: int = 180) -> str:
    line = " ".join(line.split())
    if len(line) <= limit:
        return line
    return line[: limit - 1].rsplit(" ", 1)[0] + "…"


def _truncate_chunks(
    chunks: list[RetrievedChunk], *, max_chunks: int, max_chars: int
) -> str:
    lines: list[str] = []
    for index, chunk in enumerate(chunks[:max_chunks], start=1):
        text = chunk.text.strip()
        if len(text) > max_chars:
            text = text[:max_chars].rsplit(" ", 1)[0] + "…"
        lines.append(f"[{index}] (source: {chunk.source})\n{text}")
    return "\n\n".join(lines)


def build_history(turns: list[ChatTurn]) -> str:
    """Render prior conversation turns as a readable transcript."""
    if not turns:
        return "No previous conversation."
    label = {"user": "User", "assistant": "Agent"}
    return "\n".join(f"{label.get(t.role, t.role)}: {t.content.strip()}" for t in turns)


def build_memory_context(hits: list) -> str:
    """Render retrieved memory insights as a numbered context block."""
    if not hits:
        return "No relevant learnings from past conversations."
    lines = []
    for i, hit in enumerate(hits, start=1):
        label = hit.memory_type.replace("_", " ")
        q = f"\n(Related question: {hit.source_question})" if hit.source_question else ""
        lines.append(f"[{i}] ({label}){q}\n{hit.summary.strip()}")
    return "\n\n".join(lines)


def unique_sources(chunks: list[RetrievedChunk]) -> list[str]:
    """De-duplicated list of source filenames, preserving order."""
    seen: set[str] = set()
    result: list[str] = []
    for chunk in chunks:
        if chunk.source and chunk.source not in seen:
            seen.add(chunk.source)
            result.append(chunk.source)
    return result
