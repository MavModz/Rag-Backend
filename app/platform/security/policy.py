"""Output / memory policy guards against invented instructions and policies.

Complements input sanitization: even if jailbreak phrasing slips through, answers
must stay KB-grounded for normative claims, and memory must not store ungrounded
policy text that would poison later chats.
"""
from __future__ import annotations

import re

from app.platform.observability.logging import get_logger

logger = get_logger(__name__)

# Strong normative / commercial policy claims that must be KB-backed.
_POLICY_CLAIM = re.compile(
    r"\b("
    r"refund(?:s|ed|able)?|"
    r"full\s+refund|"
    r"money[\s-]?back|"
    r"credit(?:s)?|"
    r"waive(?:d|s)?|"
    r"free\s+(?:access|forever|for\s+all)|"
    r"always\s+(?:approve|grant|give|issue)|"
    r"everyone\s+(?:gets|is\s+entitled|will\s+receive)|"
    r"all\s+(?:users|customers|students)\s+(?:get|receive|are\s+entitled)|"
    r"guaranteed\s+(?:refund|credit)|"
    r"no\s+questions?\s+asked"
    r")\b",
    re.IGNORECASE,
)

_PROMPT_LEAK = re.compile(
    r"("
    r"system\s+prompt|"
    r"hidden\s+instructions?|"
    r"my\s+instructions?\s+are|"
    r"i\s+was\s+told\s+to\s+ignore|"
    r"developer\s+message"
    r")",
    re.IGNORECASE,
)

_KB_EMPTY_MARKERS = (
    "no relevant knowledge base context was found",
    "no relevant knowledge base context",
)

POLICY_REFUSAL = (
    "I can only share policies that are documented in our knowledge base. "
    "I do not see an approved source for that claim, so I cannot confirm it. "
    "Please contact a human agent for policy decisions such as refunds or credits."
)

PROMPT_LEAK_REFUSAL = (
    "I cannot share internal instructions or system details. "
    "If you have a product or support question, I am happy to help using our docs."
)


def _kb_is_empty(kb_context: str) -> bool:
    text = (kb_context or "").strip().lower()
    if not text:
        return True
    return any(marker in text for marker in _KB_EMPTY_MARKERS)


def has_policy_claim(text: str) -> bool:
    return bool(text and _POLICY_CLAIM.search(text))


def looks_like_prompt_leak(text: str) -> bool:
    return bool(text and _PROMPT_LEAK.search(text))


def gate_answer(
    answer: str,
    *,
    sources: list[str] | None,
    kb_context: str = "",
) -> str:
    """Refuse ungrounded policy claims and prompt-leak style replies.

    Empty / whitespace-only model output is returned as ``""`` without a policy
    block — callers must not treat that as ``policy_gated``.
    """
    text = (answer or "").strip()
    if not text:
        return ""
    if looks_like_prompt_leak(text):
        logger.info("policy_guard: blocked prompt-leak style answer")
        return PROMPT_LEAK_REFUSAL
    if has_policy_claim(text) and (_kb_is_empty(kb_context) or not (sources or [])):
        logger.info("policy_guard: blocked ungrounded policy claim in answer")
        return POLICY_REFUSAL
    return text


def is_policy_refusal(answer: str) -> bool:
    """True only when ``gate_answer`` substituted a hard refusal (not empty output)."""
    return answer in (POLICY_REFUSAL, PROMPT_LEAK_REFUSAL)


def should_store_memory_insight(insight: str, sources: list[str] | None) -> bool:
    """Block persisting ungrounded normative policy into tenant memory."""
    text = (insight or "").strip()
    if not text:
        return False
    if has_policy_claim(text) and not (sources or []):
        logger.info("policy_guard: skipped memory write for ungrounded policy insight")
        return False
    if looks_like_prompt_leak(text):
        logger.info("policy_guard: skipped memory write for prompt-like insight")
        return False
    return True
