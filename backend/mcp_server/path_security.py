"""Path security utilities for Obsidian vault access.

Ensures all note paths stay within the allowed vault subdirectory (02-wiedza/).
Full implementation is deferred to Epic 38 Story 38-2.
"""

from pathlib import Path


def ensure_within_vault(relative_path: str, vault_root: Path) -> Path:
    """Resolve relative_path and verify it stays within vault_root/02-wiedza/.

    Raises raise_note_path_invalid() if path escapes the allowed area.
    Uses Path.resolve(strict=False) + is_relative_to() per architecture D4.

    Args:
        relative_path: Note path relative to vault_root/02-wiedza/ (e.g. "Kraje/Polska.md").
        vault_root: Absolute path to the Obsidian vault root directory.

    Returns:
        Resolved absolute Path to the note file.

    Raises:
        McpError: Via raise_note_path_invalid() if the resolved path escapes vault_root/02-wiedza/.
    """
    raise NotImplementedError("Implemented in Epic 38")
