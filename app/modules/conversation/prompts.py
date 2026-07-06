"""Prompt templates for the RAG chat agent."""
from __future__ import annotations

SYSTEM_PROMPT = (
    "You are a helpful customer support assistant for a company. "
    "Answer using ONLY the provided knowledge base context and prior conversation. "
    "If the answer is not in the context, say you do not have that information "
    "and offer to connect them with a human agent. "
    "Never invent facts, policies, or steps."
)

PLATFORM_HELP_SYSTEM_PROMPT = (
    "You are a helpful assistant for the AI platform product itself. "
    "Answer tenant admins using ONLY the provided platform documentation context. "
    "Help them understand how to use features: knowledge bases, ingestion, chat, "
    "API keys, provisioning, and settings. "
    "Do not use a WhatsApp or end-customer support tone. "
    "If the answer is not in the context, say you do not have that information "
    "and suggest checking the docs or contacting platform support. "
    "Never invent features, limits, or steps."
)

PROCEDURAL_SYSTEM_ADDENDUM = (
    "\n\nHow-to / procedural questions — response rules:\n"
    "- Open with ONE short sentence that directly answers the question.\n"
    "- Then numbered steps (1. 2. 3.) — one clear action per line, ~15 words max per step.\n"
    "- Use ONLY steps supported by the context. Do not invent steps.\n"
    "- If the context has no clear steps, give a brief answer in 2–4 sentences (no fake steps).\n"
    "- Cap at 6 steps unless the user explicitly asks for more detail.\n"
    "- Put an image/GIF URL on the step it illustrates (at most one link per step).\n"
    "- Do NOT paste long paragraphs or repeat the full knowledge base context.\n"
    "- Skip tangents, marketing copy, and unrelated sections from the context."
)

GENERAL_SYSTEM_ADDENDUM = (
    "\n\nGeneral questions — response rules:\n"
    "- Be concise: 2–5 sentences unless the user asks for detail.\n"
    "- Lead with the direct answer, then optional brief context.\n"
    "- Do not dump retrieved context verbatim."
)

USER_PROMPT_TEMPLATE = """\
Knowledge base context:
---------------------
{kb_context}
---------------------

Learnings from past conversations:
---------------------
{memory_context}
---------------------

Previous conversation:
---------------------
{history}
---------------------

Current user message:
{question}

{answer_instructions}"""


def build_system_prompt(*, procedural: bool = False) -> str:
    addendum = PROCEDURAL_SYSTEM_ADDENDUM if procedural else GENERAL_SYSTEM_ADDENDUM
    return SYSTEM_PROMPT + addendum


def build_platform_help_system_prompt(*, procedural: bool = False) -> str:
    addendum = PROCEDURAL_SYSTEM_ADDENDUM if procedural else GENERAL_SYSTEM_ADDENDUM
    return PLATFORM_HELP_SYSTEM_PROMPT + addendum


def build_user_prompt(
    kb_context: str,
    history: str,
    question: str,
    memory_context: str = "",
    *,
    procedural: bool = False,
) -> str:
    if not memory_context:
        memory_context = "No relevant learnings from past conversations."
    if procedural:
        answer_instructions = (
            "Answer the current user message with a crisp, step-by-step reply "
            "following the procedural rules in your system instructions."
        )
    else:
        answer_instructions = (
            "Answer the current user message concisely following your system instructions."
        )
    return USER_PROMPT_TEMPLATE.format(
        kb_context=kb_context,
        memory_context=memory_context,
        history=history,
        question=question,
        answer_instructions=answer_instructions,
    )
