"""Chatbot configuration constants."""
from __future__ import annotations

CHANNEL_WHATSAPP = "whatsapp"

KNOWN_CHANNELS = frozenset({CHANNEL_WHATSAPP})

TONE_FRIENDLY = "friendly"
TONE_PROFESSIONAL = "professional"
TONE_CONCISE = "concise"
TONE_CUSTOM = "custom"

KNOWN_TONES = frozenset({TONE_FRIENDLY, TONE_PROFESSIONAL, TONE_CONCISE, TONE_CUSTOM})

GOAL_SUPPORT = "support"
GOAL_CONVERT = "convert"
GOAL_QUALIFY = "qualify_lead"

KNOWN_GOALS = frozenset({GOAL_SUPPORT, GOAL_CONVERT, GOAL_QUALIFY})

# PromptTemplate / Configuration keys (synced on save).
PROMPT_KEY_SYSTEM = "chatbot.whatsapp.system"
CONFIG_KEY_BEHAVIOR = "chatbot.whatsapp.behavior"

TONE_INSTRUCTIONS: dict[str, str] = {
    TONE_FRIENDLY: (
        "Use a warm, approachable tone. Be encouraging and personable while staying accurate."
    ),
    TONE_PROFESSIONAL: (
        "Use a professional, clear tone. Be polite and precise; avoid slang."
    ),
    TONE_CONCISE: (
        "Be brief and direct. Short sentences; no filler. Answer first, details second."
    ),
    TONE_CUSTOM: "",
}

GOAL_INSTRUCTIONS: dict[str, str] = {
    GOAL_SUPPORT: "Primary goal: resolve the customer's question using the knowledge base.",
    GOAL_CONVERT: "Primary goal: guide the customer toward conversion (demo, signup, purchase) when relevant.",
    GOAL_QUALIFY: "Primary goal: qualify the lead (needs, timeline, contact) before deep technical detail.",
}
