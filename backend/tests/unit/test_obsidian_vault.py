"""Path-safety and versioned write/read tests for library/obsidian_vault.py
(Epic 47, Story 47.1).

Traversal test cases adapted from archived Epic 38 Story 38.2 (see
epic-47.md Story 47.1 AC #3): `../` in path, symlink outside vault, absolute
path outside vault, valid path inside the vault.

Config is mocked at the point of use (library.obsidian_vault.load_config),
not via monkeypatched env vars + reset_config() -- the global
unified_config_loader singleton is polluted by real (Vault-backed)
load_config() calls elsewhere in the full unit test suite (each of which
injects real values straight into os.environ, bypassing monkeypatch's
teardown), so an env-var-based fixture here passes in isolation but flakes
when collected alongside the rest of tests/unit/. Same pattern already used
by test_obsidian_reimport_service.py's _make_config().
"""

import os
from unittest.mock import MagicMock

import pytest

pytest.importorskip("sqlalchemy")

from library.obsidian_vault import VaultPathInvalidError, ensure_within_vault, read_note, write_note_with_version


@pytest.fixture
def vault(tmp_path, monkeypatch):
    vault_root = tmp_path / "vault"
    vault_root.mkdir()
    cfg = MagicMock()
    cfg.get.return_value = str(vault_root)
    monkeypatch.setattr("library.obsidian_vault.load_config", lambda: cfg)
    return vault_root


def test_valid_path_resolves_inside_vault(vault):
    resolved = ensure_within_vault("notes/example.md")
    assert resolved == (vault / "notes" / "example.md").resolve()


def test_rejects_dotdot_traversal(vault):
    with pytest.raises(VaultPathInvalidError):
        ensure_within_vault("../outside.md")


def test_rejects_absolute_path_outside_vault(vault, tmp_path):
    outside = tmp_path / "outside.md"
    with pytest.raises(VaultPathInvalidError):
        ensure_within_vault(str(outside))


def test_rejects_symlink_escape(vault, tmp_path):
    outside_dir = tmp_path / "outside"
    outside_dir.mkdir()
    link = vault / "escape"
    try:
        os.symlink(outside_dir, link, target_is_directory=True)
    except OSError:
        pytest.skip("symlink creation not permitted in this environment")
    with pytest.raises(VaultPathInvalidError):
        ensure_within_vault("escape/note.md")


def test_read_note_missing_file_returns_none(vault):
    assert read_note("missing.md") is None


def test_read_note_returns_content(vault):
    (vault / "note.md").write_text("hello", encoding="utf-8")
    assert read_note("note.md") == "hello"


class _FakeSession:
    def __init__(self):
        self.added = []
        self.committed = False
        self.executed = []

    def add(self, obj):
        self.added.append(obj)

    def commit(self):
        self.committed = True

    def execute(self, stmt, params=None):
        self.executed.append((str(stmt), params))


def test_write_note_with_version_new_note(vault):
    session = _FakeSession()
    version = write_note_with_version(session, "note.md", "content", tool_id=42, user_prompt="prompt")
    assert session.committed is True
    assert session.added == [version]
    assert version.content_before is None
    assert version.content_after == "content"
    assert (vault / "note.md").read_text(encoding="utf-8") == "content"


def test_write_note_with_version_existing_note(vault):
    (vault / "note.md").write_text("old", encoding="utf-8")
    session = _FakeSession()
    version = write_note_with_version(session, "note.md", "new", tool_id=1)
    assert version.content_before == "old"
    assert version.content_after == "new"
    assert (vault / "note.md").read_text(encoding="utf-8") == "new"


def test_write_note_with_version_leaves_no_temp_file(vault):
    session = _FakeSession()
    write_note_with_version(session, "note.md", "content")
    assert [p.name for p in vault.iterdir()] == ["note.md"]


def test_write_note_with_version_acquires_and_releases_advisory_lock(vault):
    session = _FakeSession()
    write_note_with_version(session, "note.md", "content")
    lock_sql = [sql for sql, _ in session.executed]
    assert len(lock_sql) == 2
    assert "pg_advisory_lock(" in lock_sql[0] and "unlock" not in lock_sql[0]
    assert "pg_advisory_unlock(" in lock_sql[1]
    # Same note_path bound param on both calls (session.executed[i][1]).
    assert session.executed[0][1] == {"note_path": "note.md"}
    assert session.executed[1][1] == {"note_path": "note.md"}


def test_advisory_lock_released_even_if_write_fails(vault, monkeypatch):
    def _boom(*_args, **_kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(os, "replace", _boom)
    session = _FakeSession()
    with pytest.raises(OSError):
        write_note_with_version(session, "note.md", "content")
    # DB commit already happened (FR20 -- not rolled back on file-write failure).
    assert session.committed is True
    lock_sql = [sql for sql, _ in session.executed]
    assert any("pg_advisory_unlock(" in sql for sql in lock_sql)


def test_write_survives_last_moment_symlink_swap(vault, tmp_path, monkeypatch):
    """Regression test for the TOCTOU race flagged in Story 47.1's code
    review: something swaps the destination for a symlink pointing outside
    the vault between ensure_within_vault()'s check and the actual write.
    os.replace() never follows a destination symlink (POSIX rename()
    replaces the directory entry itself), so the external target must stay
    untouched and the vault-local path must end up a plain file.
    """
    outside_target = tmp_path / "outside_target.md"
    outside_target.write_text("SENTINEL", encoding="utf-8")

    real_replace = os.replace

    def _swap_then_replace(src, dst):
        if os.path.lexists(dst):
            os.remove(dst)
        try:
            os.symlink(outside_target, dst)
        except OSError:
            pytest.skip("symlink creation not permitted in this environment")
        real_replace(src, dst)

    monkeypatch.setattr(os, "replace", _swap_then_replace)

    session = _FakeSession()
    write_note_with_version(session, "note.md", "attacker-controlled content")

    assert outside_target.read_text(encoding="utf-8") == "SENTINEL"
    target = vault / "note.md"
    assert not target.is_symlink()
    assert target.read_text(encoding="utf-8") == "attacker-controlled content"
