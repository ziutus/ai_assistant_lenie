"""Unit tests for obsidian_sync_config (OBSIDIAN_SYNC_SUBFOLDERS parsing)."""

from unittest.mock import MagicMock

import pytest

from library.obsidian_sync_config import (
    CONFIG_KEY,
    ObsidianSyncConfigError,
    SyncFolder,
    load_sync_folders,
    parse_sync_folders,
)


class TestParse:
    def test_valid_list(self):
        raw = '[{"path": "02-wiedza/Informatyka", "is_private": false}, {"path": "Journal", "is_private": true}]'
        assert parse_sync_folders(raw) == (
            SyncFolder("02-wiedza/Informatyka", False),
            SyncFolder("Journal", True),
        )

    def test_is_private_defaults_to_true(self):
        assert parse_sync_folders('[{"path": "X"}]') == (SyncFolder("X", True),)

    def test_empty_list_disables_sync(self):
        assert parse_sync_folders("[]") == ()

    def test_path_is_normalized(self):
        assert parse_sync_folders('[{"path": " a//b/ "}]')[0].path == "a/b"

    @pytest.mark.parametrize(
        "raw",
        [
            "",
            "   ",
            "not json",
            "{}",
            '["a"]',
            "[1]",
            "[{}]",
            '[{"path": ""}]',
            '[{"path": 5}]',
            '[{"path": "/abs"}]',
            '[{"path": "C:/x"}]',
            '[{"path": "a\\\\b"}]',
            '[{"path": "../x"}]',
            '[{"path": "a/../b"}]',
            '[{"path": "."}]',
            '[{"path": "a", "is_private": "false"}]',
            '[{"path": "a", "is_private": 0}]',
            '[{"path": "a", "extra": 1}]',
            '[{"path": "a"}, {"path": "a"}]',
            '[{"path": "a"}, {"path": "a/b"}]',
            '[{"path": "a/b"}, {"path": "a"}]',
            '[{"path": "Journal", "is_private": false}]',
            '[{"path": "Journal/2026", "is_private": false}]',
        ],
    )
    def test_invalid_values_are_rejected(self, raw):
        with pytest.raises(ObsidianSyncConfigError):
            parse_sync_folders(raw)

    def test_non_string_value_is_rejected(self):
        with pytest.raises(ObsidianSyncConfigError):
            parse_sync_folders(["a"])

    def test_similar_prefix_is_not_an_overlap(self):
        assert len(parse_sync_folders('[{"path": "a/b"}, {"path": "a/bc"}]')) == 2


def _cfg(value):
    values = {} if value is None else {CONFIG_KEY: value}
    cfg = MagicMock()
    cfg.get.side_effect = lambda key, default=None: values.get(key, default)
    return cfg


class TestLoad:
    def test_present_key_is_parsed(self):
        assert load_sync_folders(_cfg('[{"path": "X"}]')) == (SyncFolder("X", True),)

    def test_absent_key_uses_fallback(self):
        assert load_sync_folders(_cfg(None), fallback=(("A", False),)) == (SyncFolder("A", False),)

    def test_absent_key_without_fallback_means_no_sync(self):
        assert load_sync_folders(_cfg(None)) == ()

    def test_present_but_bad_key_does_not_fall_back(self):
        with pytest.raises(ObsidianSyncConfigError):
            load_sync_folders(_cfg("oops"), fallback=(("A", False),))
