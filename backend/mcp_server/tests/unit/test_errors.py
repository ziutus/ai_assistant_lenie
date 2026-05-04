"""Unit tests for mcp_server.errors — McpErrorCode enum and helper raise functions."""

import pytest

pytest.importorskip("mcp")  # Skip module if mcp is not installed (e.g. uvx isolated env)

from mcp import McpError

from mcp_server.errors import (
    McpErrorCode,
    raise_article_not_found,
    raise_database_unavailable,
    raise_note_not_found,
    raise_note_path_invalid,
    raise_vault_write_failed,
    raise_version_save_failed,
)


class TestMcpErrorCode:
    def test_all_codes_in_json_rpc_range(self):
        for code in McpErrorCode:
            assert -32099 <= code <= -32000, f"{code.name}={code} outside -32000..-32099"

    def test_expected_codes(self):
        assert McpErrorCode.ARTICLE_NOT_FOUND == -32001
        assert McpErrorCode.NOTE_NOT_FOUND == -32002
        assert McpErrorCode.NOTE_PATH_INVALID == -32003
        assert McpErrorCode.VAULT_WRITE_FAILED == -32004
        assert McpErrorCode.DATABASE_UNAVAILABLE == -32005
        assert McpErrorCode.VERSION_SAVE_FAILED == -32006

    def test_six_codes_defined(self):
        assert len(McpErrorCode) == 6


class TestRaiseArticleNotFound:
    def test_raises_mcp_error(self):
        with pytest.raises(McpError):
            raise_article_not_found(99)

    def test_correct_error_code(self):
        with pytest.raises(McpError) as exc_info:
            raise_article_not_found(42)
        assert exc_info.value.error.code == McpErrorCode.ARTICLE_NOT_FOUND

    def test_message_contains_id(self):
        with pytest.raises(McpError) as exc_info:
            raise_article_not_found(123)
        assert "123" in exc_info.value.error.message

    def test_message_contains_polish_text(self):
        with pytest.raises(McpError) as exc_info:
            raise_article_not_found(1)
        assert "usunięty" in exc_info.value.error.message


class TestRaiseNoteNotFound:
    def test_raises_mcp_error(self):
        with pytest.raises(McpError):
            raise_note_not_found("Kraje/Polska.md")

    def test_correct_error_code(self):
        with pytest.raises(McpError) as exc_info:
            raise_note_not_found("some/path.md")
        assert exc_info.value.error.code == McpErrorCode.NOTE_NOT_FOUND

    def test_message_contains_path(self):
        with pytest.raises(McpError) as exc_info:
            raise_note_not_found("Kraje/Polska.md")
        assert "Kraje/Polska.md" in exc_info.value.error.message


class TestRaiseNotePathInvalid:
    def test_raises_mcp_error(self):
        with pytest.raises(McpError):
            raise_note_path_invalid("../secret.md")

    def test_correct_error_code(self):
        with pytest.raises(McpError) as exc_info:
            raise_note_path_invalid("../escape.md")
        assert exc_info.value.error.code == McpErrorCode.NOTE_PATH_INVALID

    def test_message_contains_path(self):
        with pytest.raises(McpError) as exc_info:
            raise_note_path_invalid("../evil.md")
        assert "../evil.md" in exc_info.value.error.message


class TestRaiseVaultWriteFailed:
    def test_raises_mcp_error(self):
        with pytest.raises(McpError):
            raise_vault_write_failed()

    def test_correct_error_code(self):
        with pytest.raises(McpError) as exc_info:
            raise_vault_write_failed()
        assert exc_info.value.error.code == McpErrorCode.VAULT_WRITE_FAILED

    def test_without_detail(self):
        with pytest.raises(McpError) as exc_info:
            raise_vault_write_failed()
        assert "Sync" in exc_info.value.error.message

    def test_with_detail(self):
        with pytest.raises(McpError) as exc_info:
            raise_vault_write_failed("no space left")
        assert "no space left" in exc_info.value.error.message


class TestRaiseDatabaseUnavailable:
    def test_raises_mcp_error(self):
        with pytest.raises(McpError):
            raise_database_unavailable()

    def test_correct_error_code(self):
        with pytest.raises(McpError) as exc_info:
            raise_database_unavailable()
        assert exc_info.value.error.code == McpErrorCode.DATABASE_UNAVAILABLE

    def test_message_mentions_nas(self):
        with pytest.raises(McpError) as exc_info:
            raise_database_unavailable()
        assert "NAS" in exc_info.value.error.message


class TestRaiseVersionSaveFailed:
    def test_raises_mcp_error(self):
        with pytest.raises(McpError):
            raise_version_save_failed()

    def test_correct_error_code(self):
        with pytest.raises(McpError) as exc_info:
            raise_version_save_failed()
        assert exc_info.value.error.code == McpErrorCode.VERSION_SAVE_FAILED

    def test_message_indicates_note_unchanged(self):
        with pytest.raises(McpError) as exc_info:
            raise_version_save_failed()
        assert "nie została zmieniona" in exc_info.value.error.message
