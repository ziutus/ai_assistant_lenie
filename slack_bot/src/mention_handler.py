"""Channel @mention handler for Lenie Slack Bot.

Routes @Lenie mentions in channels to the same command handlers used
by DM messages. All responses are posted as thread replies to keep
channels clean.
"""

from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING

from src.dm_handler import (
    HELP_TEXT,
    _route_intent,
    handle_add,
    handle_check,
    handle_count,
    handle_info,
    handle_search,
    handle_version,
)
from src.intent_parser import parse_intent

if TYPE_CHECKING:
    from slack_bolt import App

    from src.api_client import LenieApiClient

logger = logging.getLogger(__name__)

_BOT_MENTION_RE = re.compile(r"<@[A-Z0-9]+>\s*")


def _strip_mention(text: str) -> str:
    """Remove the leading bot mention (e.g. ``<@U123ABC>``) from event text."""
    return _BOT_MENTION_RE.sub("", text, count=1).strip()


def register_mention_handler(app: App, client: LenieApiClient, intent_enabled: bool = False) -> None:
    """Register app_mention event handler on the Slack Bolt app."""
    logger.info("Registering app_mention handler (intent_parsing=%s)", intent_enabled)

    commands = {
        "version": lambda say, args: handle_version(say, client),
        "count": lambda say, args: handle_count(say, client),
        "search": lambda say, args: handle_search(say, client, args),
        "add": lambda say, args: handle_add(say, client, args),
        "check": lambda say, args: handle_check(say, client, args),
        "info": lambda say, args: handle_info(say, client, args),
        "help": lambda say, args: say(text=HELP_TEXT),
    }

    @app.event("app_mention")
    def handle_app_mention(event, say):
        if event.get("bot_id"):
            return

        thread_ts = event.get("ts")
        threaded_say = lambda **kw: say(thread_ts=thread_ts, **kw)  # noqa: E731

        raw_text = event.get("text") or ""
        text = _strip_mention(raw_text)

        if not text:
            threaded_say(text=HELP_TEXT)
            return

        # 1. Try keyword matching first (instant, no LLM cost)
        parts = text.split(maxsplit=1)
        command = parts[0].lower()
        args_str = parts[1] if len(parts) > 1 else ""

        handler = commands.get(command)
        if handler:
            handler(threaded_say, args_str)
            return

        # 2. If no keyword match and intent parsing enabled, try LLM
        if intent_enabled:
            intent = parse_intent(client, text)
            if intent and intent.command != "unknown":
                if _route_intent(intent, threaded_say, commands):
                    return
                threaded_say(text=f"I understood your request ({intent.command}), but this command is not yet available. {HELP_TEXT}")
                return
            if intent and intent.command == "unknown":
                threaded_say(text=f"I'm not sure what you mean. {HELP_TEXT}")
                return
            # intent is None (LLM unreachable) — fall through to help

        threaded_say(text=f"I didn't understand that. {HELP_TEXT}")
