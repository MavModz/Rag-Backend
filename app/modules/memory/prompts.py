"""Prompts for memory reflection (distilling chat turns into storable insights)."""
from __future__ import annotations

REFLECT_USER_TEMPLATE = """\
Extract ONE concise factual insight from this support exchange that would help \
answer similar future questions for other customers. Focus on policies, \
procedures, or recurring clarifications — not greetings or small talk.

If nothing worth remembering, respond with exactly: NONE

User question:
{question}

Assistant answer:
{answer}

Sources used: {sources}

Insight (one or two sentences, or NONE):"""


def build_reflect_prompt(question: str, answer: str, sources: list[str]) -> str:
    src = ", ".join(sources) if sources else "(none)"
    return REFLECT_USER_TEMPLATE.format(question=question.strip(), answer=answer.strip(), sources=src)
