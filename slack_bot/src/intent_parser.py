"""Intent parser client for Lenie Slack Bot.

Calls the backend /ai_parse_intent endpoint to classify natural language
messages into structured commands. Returns ParsedIntent dataclass or None
on failure (enabling graceful fallback to keyword matching).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

from src.api_client import ApiConnectionError, ApiError

if TYPE_CHECKING:
    from src.api_client import LenieApiClient

logger = logging.getLogger(__name__)


@dataclass
class ParsedIntent:
    """Structured result from LLM intent parsing."""
    command: str
    args: dict
    confidence: float


def parse_intent(client: LenieApiClient, text: str) -> ParsedIntent | None:
    """Parse natural language text into a command intent via backend LLM.

    Args:
        client: Configured LenieApiClient instance.
        text: Raw user message text.

    Returns:
        ParsedIntent if backend successfully parsed the intent,
        None if backend is unreachable or returns an error (fallback signal).
    """
    try:
        data = client.parse_intent(text)
        return ParsedIntent(
            command=data.get("command", "unknown"),
            args=data.get("args", {}),
            confidence=data.get("confidence", 0.0),
        )
    except ApiConnectionError:
        logger.warning("Intent parser backend unreachable — falling back to keyword matching")
        return None
    except ApiError as exc:
        logger.warning("Intent parser error: %s — falling back to keyword matching", exc.message)
        return None
    except Exception:
        logger.exception("Unexpected error in intent parser")
        return None
