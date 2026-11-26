"""The parts of the live agent the text simulation reuses.

One place to import them from, so the checks always run against the same
prompt, tools, model settings and reply clean-up as a real call.
"""

from __future__ import annotations

import re

from app import clinic
from app.agent import guards, tools
from app.agent.processors import ReplyCutter
from app.agent.prompt import GREETING, system_prompt
from app.config import get_settings

__all__ = ["GREETING", "MODEL", "clean_reply", "clinic", "guards", "settings", "system_prompt", "tools"]

MODEL = get_settings().groq_model


def settings() -> dict:
    """The request settings the live pipeline gives the model."""
    return get_settings().llm_request


def clean_reply(text: str) -> str:
    """What OneQuestionGate lets through: nothing after the first question."""
    return re.sub(r"\s+", " ", ReplyCutter().feed(text)).strip()
