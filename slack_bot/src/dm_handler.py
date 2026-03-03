"""DM text command handler for Lenie Slack Bot.

Parses plain text messages in direct messages and routes them
to the appropriate command handler. Provides the same functionality
as slash commands but via conversational DM interface.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from src.api_client import (
    ApiConnectionError,
    ApiError,
    ApiResponseError,
)
from src.commands import DOCUMENT_TYPES, _VALID_TYPES

if TYPE_CHECKING:
    from collections.abc import Callable

    from slack_bolt import App

    from src.api_client import LenieApiClient

logger = logging.getLogger(__name__)

HELP_TEXT = (
    "Available commands:\n"
    "  version  — Show backend version and build info\n"
    "  count    — Show document count by type\n"
    "  add <url> [type]  — Add a URL to the knowledge base\n"
    "  check <url>  — Check if a URL exists in the database\n"
    "  info <id>  — Get document details by ID\n"
    "  help     — Show this help message\n"
    f"\nTypes: {', '.join(DOCUMENT_TYPES)} (default: webpage)"
)


def _handle_version(say: Callable, client: LenieApiClient) -> None:
    """Handle 'version' DM command."""
    try:
        data = client.get_version()
        say(text=f"Version: {data['app_version']}\nBuild: {data['app_build_time']}")
    except ApiConnectionError:
        say(text="Backend unreachable (connection timeout). Check if lenie-ai-server is running.")
    except ApiResponseError as exc:
        logger.warning("Unexpected response from backend: %s", exc.message)
        say(text=f"Unexpected response from backend (HTTP {exc.status_code})")
    except ApiError as exc:
        say(text=f"An error occurred: {exc.message}")
    except KeyError as exc:
        logger.warning("Unexpected version response format: missing key %s", exc)
        say(text="Unexpected response from backend")


def _handle_count(say: Callable, client: LenieApiClient) -> None:
    """Handle 'count' DM command."""
    try:
        counts = client.get_all_counts()
        total = counts.get("ALL", 0)
        lines = [f"Documents in knowledge base: {total:,} total", ""]

        for doc_type in DOCUMENT_TYPES:
            count = counts.get(doc_type, 0)
            if count > 0:
                lines.append(f"  {doc_type}: {count:,}")

        say(text="\n".join(lines))
    except ApiConnectionError:
        say(text="Backend unreachable (connection timeout). Check if lenie-ai-server is running.")
    except ApiResponseError as exc:
        logger.warning("Unexpected response from backend: %s", exc.message)
        say(text=f"Unexpected response from backend (HTTP {exc.status_code})")
    except ApiError as exc:
        say(text=f"An error occurred: {exc.message}")
    except KeyError as exc:
        logger.warning("Unexpected count response format: missing key %s", exc)
        say(text="Unexpected response from backend")


def _handle_add(say: Callable, client: LenieApiClient, args_str: str) -> None:
    """Handle 'add <url> [type]' DM command."""
    parts = args_str.strip().split()
    if not parts:
        say(text=f"Usage: `add <url> [type]`\nTypes: {', '.join(DOCUMENT_TYPES)} (default: webpage)")
        return
    url = parts[0]
    if not url.startswith(("http://", "https://")):
        say(text="URL must start with `http://` or `https://`")
        return
    if len(parts) > 2:
        say(text=f"Too many arguments. Usage: `add <url> [type]`\nTypes: {', '.join(DOCUMENT_TYPES)} (default: webpage)")
        return
    url_type = parts[1] if len(parts) > 1 else "webpage"
    if url_type not in _VALID_TYPES:
        say(text=f"Unknown type `{url_type}`. Valid: {', '.join(sorted(_VALID_TYPES))}")
        return
    try:
        data = client.add_url(url, url_type=url_type)
        say(text=f"Added to knowledge base (ID: {data['document_id']}). Type: {url_type}.")
    except ApiConnectionError:
        say(text="Backend unreachable (connection timeout). Check if lenie-ai-server is running.")
    except ApiResponseError as exc:
        logger.warning("Unexpected response from backend: %s", exc.message)
        say(text=f"Unexpected response from backend (HTTP {exc.status_code})")
    except ApiError as exc:
        say(text=f"An error occurred: {exc.message}")
    except KeyError as exc:
        logger.warning("Unexpected add_url response format: missing key %s", exc)
        say(text="Unexpected response from backend")


def _handle_check(say: Callable, client: LenieApiClient, args_str: str) -> None:
    """Handle 'check <url>' DM command."""
    url = args_str.strip()
    if not url:
        say(text="Usage: `check <url>`")
        return
    if not url.startswith(("http://", "https://")):
        say(text="URL must start with `http://` or `https://`")
        return
    try:
        result = client.check_url(url)
        if result is not None:
            say(
                text=f"Found in database (ID: {result['id']}). "
                f"Type: {result['document_type']}. "
                f"Status: {result['document_state']}. "
                f"Added: {result['created_at']}."
            )
        else:
            say(text="Not found in database.")
    except ApiConnectionError:
        say(text="Backend unreachable (connection timeout). Check if lenie-ai-server is running.")
    except ApiResponseError as exc:
        logger.warning("Unexpected response from backend: %s", exc.message)
        say(text=f"Unexpected response from backend (HTTP {exc.status_code})")
    except ApiError as exc:
        say(text=f"An error occurred: {exc.message}")
    except KeyError as exc:
        logger.warning("Unexpected check_url response format: missing key %s", exc)
        say(text="Unexpected response from backend")


def _handle_info(say: Callable, client: LenieApiClient, args_str: str) -> None:
    """Handle 'info <id>' DM command."""
    text_input = args_str.strip()
    if not text_input:
        say(text="Usage: `info <document_id>` (numeric ID required)")
        return
    try:
        document_id = int(text_input)
    except ValueError:
        say(text="Usage: `info <document_id>` (numeric ID required)")
        return
    try:
        data = client.get_document(document_id)
        say(
            text=f"Document #{document_id}\n"
            f"Title: {data['title']}\n"
            f"Type: {data['document_type']}\n"
            f"Status: {data['document_state']}\n"
            f"Added: {data['created_at']}"
        )
    except ApiConnectionError:
        say(text="Backend unreachable (connection timeout). Check if lenie-ai-server is running.")
    except ApiResponseError as exc:
        logger.warning("Unexpected response from backend: %s", exc.message)
        say(text=f"Unexpected response from backend (HTTP {exc.status_code})")
    except ApiError as exc:
        say(text=f"An error occurred: {exc.message}")
    except KeyError as exc:
        logger.warning("Unexpected get_document response format: missing key %s", exc)
        say(text="Unexpected response from backend")


def register_dm_handler(app: App, client: LenieApiClient) -> None:
    """Register DM message event handler on the Slack Bolt app."""
    logger.info("Registering DM message handler")

    commands = {
        "version": lambda say, args: _handle_version(say, client),
        "count": lambda say, args: _handle_count(say, client),
        "add": lambda say, args: _handle_add(say, client, args),
        "check": lambda say, args: _handle_check(say, client, args),
        "info": lambda say, args: _handle_info(say, client, args),
        "help": lambda say, args: say(text=HELP_TEXT),
    }

    @app.event("message")
    def handle_message(event, say):
        # Only handle DM messages
        if event.get("channel_type") != "im":
            return

        # Skip bot's own messages to prevent infinite loops
        if event.get("bot_id"):
            return

        # Skip message subtypes (edits, deletes, thread broadcasts, etc.)
        if event.get("subtype"):
            return

        text = (event.get("text") or "").strip()
        if not text:
            say(text=HELP_TEXT)
            return

        parts = text.split(maxsplit=1)
        command = parts[0].lower()
        args_str = parts[1] if len(parts) > 1 else ""

        handler = commands.get(command)
        if handler:
            handler(say, args_str)
        else:
            say(text=f"I didn't understand that. {HELP_TEXT}")
