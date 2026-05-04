"""MCP error codes and helper functions for raising typed McpError exceptions.

All error codes use the JSON-RPC application-error range: -32000..-32099.
Polish user-facing messages are sourced from the PRD error contract (verbatim base text).
Where applicable, helpers append machine-readable context (id=..., path=...) after the
Polish sentence to aid debugging — the user-visible message still starts with the PRD text.
"""

from enum import IntEnum
from typing import NoReturn

from mcp import McpError
from mcp.types import ErrorData


class McpErrorCode(IntEnum):
    ARTICLE_NOT_FOUND = -32001
    NOTE_NOT_FOUND = -32002
    NOTE_PATH_INVALID = -32003
    VAULT_WRITE_FAILED = -32004
    DATABASE_UNAVAILABLE = -32005
    VERSION_SAVE_FAILED = -32006


def raise_article_not_found(article_id: int) -> NoReturn:
    """Raise McpError when the requested article does not exist in the database."""
    raise McpError(
        ErrorData(
            code=McpErrorCode.ARTICLE_NOT_FOUND,
            message=f"Nie znalazłem artykułu o tym ID — możliwe że został wcześniej usunięty. (id={article_id})",
        )
    )


def raise_note_not_found(path: str) -> NoReturn:
    """Raise McpError when the requested Obsidian note does not exist."""
    raise McpError(
        ErrorData(
            code=McpErrorCode.NOTE_NOT_FOUND,
            message=f"Nie ma notatki pod tą ścieżką w 02-wiedza/. (path={path})",
        )
    )


def raise_note_path_invalid(path: str) -> NoReturn:
    """Raise McpError when the given path escapes the allowed vault area."""
    raise McpError(
        ErrorData(
            code=McpErrorCode.NOTE_PATH_INVALID,
            message=f"Ścieżka jest poza dozwolonym obszarem 02-wiedza/. (path={path})",
        )
    )


def raise_vault_write_failed(detail: str = "") -> NoReturn:
    """Raise McpError when writing a note to the Obsidian vault fails."""
    suffix = f" ({detail})" if detail else ""
    raise McpError(
        ErrorData(
            code=McpErrorCode.VAULT_WRITE_FAILED,
            message=f"Nie udało się zapisać notatki — sprawdź miejsce na dysku i status Obsidian Sync.{suffix}",
        )
    )


def raise_database_unavailable() -> NoReturn:
    """Raise McpError when the Lenie database cannot be reached."""
    raise McpError(
        ErrorData(
            code=McpErrorCode.DATABASE_UNAVAILABLE,
            message="Baza Lenie jest niedostępna — sprawdź czy NAS i kontener lenie-ai-db działają.",
        )
    )


def raise_version_save_failed() -> NoReturn:
    """Raise McpError when saving a historical note version fails (note is NOT modified)."""
    raise McpError(
        ErrorData(
            code=McpErrorCode.VERSION_SAVE_FAILED,
            message="Wstrzymałem zapis notatki — nie mogłem zapisać wersji historycznej. Notatka nie została zmieniona.",
        )
    )
