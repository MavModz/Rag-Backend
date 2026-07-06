"""Import side-effect module that registers every ORM model on ``Base.metadata``.

Alembic's ``env.py`` and the seed/bootstrap scripts import this so the full
schema is known from a single place. Add new model modules here when a service
is activated.
"""
from __future__ import annotations

# noqa: F401 — imported for their registration side effects.
from app.jobs import models as _jobs  # noqa: F401
from app.modules.chatbot import models as _chatbot  # noqa: F401
from app.modules.conversation import models as _conversation  # noqa: F401
from app.modules.identity import models as _identity  # noqa: F401
from app.modules.knowledge import models as _knowledge  # noqa: F401
from app.modules.memory import models as _memory  # noqa: F401
from app.modules.model_gateway import models as _model_gateway  # noqa: F401
from app.platform.connectors import models as _connectors  # noqa: F401
from app.platform.db.base import Base

metadata = Base.metadata

__all__ = ["Base", "metadata"]
