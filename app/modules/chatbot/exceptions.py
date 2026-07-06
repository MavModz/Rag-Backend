"""Chatbot domain exceptions."""


class ChatbotError(Exception):
    """Base chatbot error."""


class ChatbotDisabledError(ChatbotError):
    """Raised when chatbot is configured but disabled for the channel."""


class ChatbotVersionConflictError(ChatbotError):
    """Optimistic-lock failure on config update."""

    def __init__(self, expected: int, actual: int) -> None:
        self.expected = expected
        self.actual = actual
        super().__init__(f"Config version conflict: expected {expected}, got {actual}")


class ChatbotSchemaNotReadyError(ChatbotError):
    """Raised when the chatbot_configs table has not been created (migration pending)."""
