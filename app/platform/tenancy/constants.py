"""Product, agent, and auth-mode constants for request context."""
from __future__ import annotations

from app.modules.knowledge.constants import DEFAULT_KB_SCOPE

PRODUCT_LMS = "lms"
PRODUCT_CRM = "crm"
KNOWN_PRODUCTS = frozenset({PRODUCT_LMS, PRODUCT_CRM})

AGENT_SUPPORT = "support"
AGENT_QUIZ = "quiz"
AGENT_MEETING = "meeting"
AGENT_WHATSAPP = "whatsapp"
AGENT_PLATFORM_HELP = "platform_help"
KNOWN_AGENTS = frozenset(
    {AGENT_SUPPORT, AGENT_QUIZ, AGENT_MEETING, AGENT_WHATSAPP, AGENT_PLATFORM_HELP}
)

# Agent slug -> knowledge-base scope used at retrieval time (WhatsApp may override from config).
AGENT_KB_SCOPE: dict[str, str] = {
    AGENT_SUPPORT: DEFAULT_KB_SCOPE,
    AGENT_QUIZ: "quiz",
    AGENT_MEETING: "meeting",
    AGENT_WHATSAPP: DEFAULT_KB_SCOPE,
    AGENT_PLATFORM_HELP: DEFAULT_KB_SCOPE,
}

# Retrieval layer per agent.
RETRIEVAL_PLATFORM_ONLY = "platform_only"
RETRIEVAL_TENANT_ONLY = "tenant_only"
RETRIEVAL_PLATFORM_AND_TENANT = "platform_and_tenant"

AGENT_RETRIEVAL_PROFILE: dict[str, str] = {
    AGENT_PLATFORM_HELP: RETRIEVAL_PLATFORM_ONLY,
    AGENT_WHATSAPP: RETRIEVAL_TENANT_ONLY,
    AGENT_SUPPORT: RETRIEVAL_PLATFORM_AND_TENANT,
    AGENT_QUIZ: RETRIEVAL_TENANT_ONLY,
    AGENT_MEETING: RETRIEVAL_TENANT_ONLY,
}

# System prompt source per agent.
PROMPT_PLATFORM_HELP = "platform_help"
PROMPT_CHATBOT = "chatbot"
PROMPT_DEFAULT = "default"

AGENT_PROMPT_SOURCE: dict[str, str] = {
    AGENT_PLATFORM_HELP: PROMPT_PLATFORM_HELP,
    AGENT_WHATSAPP: PROMPT_CHATBOT,
}


class AuthMode:
    """How the caller authenticated to the AI platform."""

    ANONYMOUS = "anonymous"
    API_KEY = "api_key"
    PLATFORM_JWT = "platform_jwt"
    PRODUCT_USER_JWT = "product_user_jwt"
    API_KEY_PRODUCT_USER = "api_key_product_user"
