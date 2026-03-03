"""Slack slash command handlers.

Implements /lenie-version, /lenie-count, /lenie-check, /lenie-add, /lenie-info.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from src.api_client import (
    ApiConnectionError,
    ApiError,
    ApiResponseError,
    LenieApiClient,
)

if TYPE_CHECKING:
    from collections.abc import Callable

    from slack_bolt import App

logger = logging.getLogger(__name__)

DOCUMENT_TYPES = ("webpage", "youtube", "link", "movie", "text_message", "text")


def _handle_version(ack: Callable, respond: Callable, client: LenieApiClient) -> None:
    """Handle /lenie-version command — return backend version info."""
    ack()
    try:
        data = client.get_version()
        respond(text=f"Version: {data['app_version']}\nBuild: {data['app_build_time']}")
    except ApiConnectionError:
        respond(text="Backend unreachable (connection timeout). Check if lenie-ai-server is running.")
    except ApiResponseError as exc:
        logger.warning("Unexpected response from backend: %s", exc.message)
        respond(text=f"Unexpected response from backend (HTTP {exc.status_code})")
    except ApiError as exc:
        respond(text=f"An error occurred: {exc.message}")
    except KeyError as exc:
        logger.warning("Unexpected version response format: missing key %s", exc)
        respond(text="Unexpected response from backend")


def _handle_count(ack: Callable, respond: Callable, client: LenieApiClient) -> None:
    """Handle /lenie-count command — return document count breakdown."""
    ack()
    try:
        total = client.get_count("ALL")
        lines = [f"Documents in knowledge base: {total:,} total", ""]

        for doc_type in DOCUMENT_TYPES:
            count = client.get_count(doc_type)
            if count > 0:
                lines.append(f"  {doc_type}: {count:,}")

        respond(text="\n".join(lines))
    except ApiConnectionError:
        respond(text="Backend unreachable (connection timeout). Check if lenie-ai-server is running.")
    except ApiResponseError as exc:
        logger.warning("Unexpected response from backend: %s", exc.message)
        respond(text=f"Unexpected response from backend (HTTP {exc.status_code})")
    except ApiError as exc:
        respond(text=f"An error occurred: {exc.message}")


_VALID_TYPES = frozenset(DOCUMENT_TYPES)


def _handle_add(ack: Callable, respond: Callable, client: LenieApiClient, command: dict) -> None:
    """Handle /lenie-add command — add a URL to the knowledge base."""
    ack()
    parts = command.get("text", "").strip().split()
    if not parts:
        respond(text=f"Usage: `/lenie-add <url> [type]`\nTypes: {', '.join(DOCUMENT_TYPES)} (default: webpage)")
        return
    url = parts[0]
    url_type = parts[1] if len(parts) > 1 else "webpage"
    if url_type not in _VALID_TYPES:
        respond(text=f"Unknown type `{url_type}`. Valid: {', '.join(sorted(_VALID_TYPES))}")
        return
    try:
        data = client.add_url(url, url_type=url_type)
        respond(text=f"Added to knowledge base (ID: {data['document_id']}). Type: {url_type}.")
    except ApiConnectionError:
        respond(text="Backend unreachable (connection timeout). Check if lenie-ai-server is running.")
    except ApiResponseError as exc:
        logger.warning("Unexpected response from backend: %s", exc.message)
        respond(text=f"Unexpected response from backend (HTTP {exc.status_code})")
    except ApiError as exc:
        respond(text=f"An error occurred: {exc.message}")
    except KeyError as exc:
        logger.warning("Unexpected add_url response format: missing key %s", exc)
        respond(text="Unexpected response from backend")


def _handle_check(ack: Callable, respond: Callable, client: LenieApiClient, command: dict) -> None:
    """Handle /lenie-check command — check if a URL exists in the knowledge base."""
    ack()
    url = command.get("text", "").strip()
    if not url:
        respond(text="Usage: `/lenie-check <url>`")
        return
    try:
        result = client.check_url(url)
        if result is not None:
            respond(
                text=f"Found in database (ID: {result['id']}). "
                f"Type: {result['document_type']}. "
                f"Status: {result['document_state']}. "
                f"Added: {result['created_at']}."
            )
        else:
            respond(text="Not found in database.")
    except ApiConnectionError:
        respond(text="Backend unreachable (connection timeout). Check if lenie-ai-server is running.")
    except ApiResponseError as exc:
        logger.warning("Unexpected response from backend: %s", exc.message)
        respond(text=f"Unexpected response from backend (HTTP {exc.status_code})")
    except ApiError as exc:
        respond(text=f"An error occurred: {exc.message}")
    except KeyError as exc:
        logger.warning("Unexpected check_url response format: missing key %s", exc)
        respond(text="Unexpected response from backend")


def _handle_info(ack: Callable, respond: Callable, client: LenieApiClient, command: dict) -> None:
    """Handle /lenie-info command — get document details by ID."""
    ack()
    text_input = command.get("text", "").strip()
    if not text_input:
        respond(text="Usage: `/lenie-info <document_id>` (numeric ID required)")
        return
    try:
        document_id = int(text_input)
    except ValueError:
        respond(text="Usage: `/lenie-info <document_id>` (numeric ID required)")
        return
    try:
        data = client.get_document(document_id)
        respond(
            text=f"Document #{document_id}\n"
            f"Title: {data['title']}\n"
            f"Type: {data['document_type']}\n"
            f"Status: {data['document_state']}\n"
            f"Added: {data['created_at']}"
        )
    except ApiConnectionError:
        respond(text="Backend unreachable (connection timeout). Check if lenie-ai-server is running.")
    except ApiResponseError as exc:
        logger.warning("Unexpected response from backend: %s", exc.message)
        respond(text=f"Unexpected response from backend (HTTP {exc.status_code})")
    except ApiError as exc:
        respond(text=f"An error occurred: {exc.message}")
    except KeyError as exc:
        logger.warning("Unexpected get_document response format: missing key %s", exc)
        respond(text="Unexpected response from backend")


def register_commands(app: App, client: LenieApiClient) -> None:
    """Register all slash commands on the Slack Bolt app."""
    logger.info("Registering slash commands")

    @app.command("/lenie-version")
    def handle_version(ack, respond):
        _handle_version(ack, respond, client)

    @app.command("/lenie-count")
    def handle_count(ack, respond):
        _handle_count(ack, respond, client)

    @app.command("/lenie-add")
    def handle_add(ack, respond, command):
        _handle_add(ack, respond, client, command)

    @app.command("/lenie-check")
    def handle_check(ack, respond, command):
        _handle_check(ack, respond, client, command)

    @app.command("/lenie-info")
    def handle_info(ack, respond, command):
        _handle_info(ack, respond, client, command)
