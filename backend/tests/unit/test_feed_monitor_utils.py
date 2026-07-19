"""Unit tests for pure helper functions in imports.feed_monitor.

feed_monitor imports DB/network modules at module level (sqlalchemy, requests,
yaml, library.db.*). In the lightweight uvx pytest environment those are not
installed, so minimal stubs are injected into sys.modules just for the import
of the module under test, then removed — other test modules (which use
pytest.importorskip on the real packages) are unaffected. In a full venv the
real modules are used. The tested functions never touch the stubbed modules.
"""

import importlib
import sys
import types
from datetime import date

import pytest

_STUBBED: list[str] = []


def _ensure_importable(name: str, **attrs):
    """Install a stub module under `name` if the real one cannot be imported."""
    try:
        importlib.import_module(name)
        return
    except ImportError:
        pass
    parent_name, _, child = name.rpartition(".")
    if parent_name:
        _ensure_importable(parent_name)
    module = types.ModuleType(name)
    for key, value in attrs.items():
        setattr(module, key, value)
    sys.modules[name] = module
    _STUBBED.append(name)
    if parent_name:
        setattr(sys.modules[parent_name], child, module)


def _remove_stubs():
    """Drop stub modules so importorskip-based tests still see them as missing."""
    for name in reversed(_STUBBED):
        sys.modules.pop(name, None)
        parent_name, _, child = name.rpartition(".")
        parent = sys.modules.get(parent_name)
        if parent is not None:
            try:
                delattr(parent, child)
            except AttributeError:
                pass
    _STUBBED.clear()


_ensure_importable("requests")
_ensure_importable("yaml")
_ensure_importable("sqlalchemy", select=lambda *a, **k: None,
                   or_=lambda *a, **k: None, text=lambda *a, **k: None)
_ensure_importable("sqlalchemy.exc",
                   SQLAlchemyError=type("SQLAlchemyError", (Exception,), {}),
                   OperationalError=type("OperationalError", (Exception,), {}),
                   InternalError=type("InternalError", (Exception,), {}))
_ensure_importable("library.config_loader",
                   load_config=lambda: types.SimpleNamespace(
                       get=lambda *a, **k: None, require=lambda *a, **k: ""))
_ensure_importable("library.db.engine", get_session=lambda: None)
_ensure_importable("library.db.models",
                   ImportLog=type("ImportLog", (), {}),
                   Document=type("Document", (), {}))
_ensure_importable("library.document_service", DocumentService=type("DocumentService", (), {}))
_ensure_importable("library.import_log_tracker", ImportLogTracker=type("ImportLogTracker", (), {}))
_ensure_importable("library.stalker_web_documents_db_postgresql",
                   WebsitesDBPostgreSQL=type("WebsitesDBPostgreSQL", (), {}))

try:
    from imports.feed_monitor import (
        _parse_selection,
        apply_skip_filters,
        build_feed_url,
        detect_document_type,
        parse_date,
        resolve_default_state,
        strip_html,
    )
finally:
    _remove_stubs()


class TestParseDate:
    def test_iso_date(self):
        assert parse_date("2026-03-01") == date(2026, 3, 1)

    def test_iso_datetime_utc(self):
        assert parse_date("2026-03-01T12:30:00+00:00") == date(2026, 3, 1)

    def test_rfc2822(self):
        assert parse_date("Mon, 02 Mar 2026 10:00:00 +0000") == date(2026, 3, 2)

    def test_empty_string(self):
        assert parse_date("") is None

    def test_garbage(self):
        assert parse_date("wczoraj wieczorem") is None


class TestStripHtml:
    def test_plain_text_unchanged(self):
        assert strip_html("Zwykły tekst bez tagów.") == "Zwykły tekst bez tagów."

    def test_br_becomes_newline(self):
        assert strip_html("linia1<br>linia2<br/>linia3") == "linia1\nlinia2\nlinia3"

    def test_list_items_become_bullets(self):
        result = strip_html("<ul><li>jeden</li><li>dwa</li></ul>")
        assert "- jeden" in result
        assert "- dwa" in result

    def test_link_keeps_text_and_url(self):
        result = strip_html('Zobacz <a href="https://example.com">stronę</a>.')
        assert result == "Zobacz stronę (https://example.com)."

    def test_entities_decoded(self):
        assert strip_html("<p>A &amp; B &lt;C&gt;</p>") == "A & B <C>"

    def test_multiple_blank_lines_collapsed(self):
        result = strip_html("<p>akapit1</p><p></p><p></p><p>akapit2</p>")
        assert "\n\n\n" not in result


class TestParseSelection:
    def test_comma_separated(self):
        assert _parse_selection("1,3,5", {1, 2, 3, 4, 5}) == {1, 3, 5}

    def test_range(self):
        assert _parse_selection("2-4", {1, 2, 3, 4, 5}) == {2, 3, 4}

    def test_mixed(self):
        assert _parse_selection("1,3-4", {1, 2, 3, 4, 5}) == {1, 3, 4}

    def test_all(self):
        assert _parse_selection("all", {1, 2, 3}) == {1, 2, 3}

    def test_none_and_empty(self):
        assert _parse_selection("none", {1, 2}) == set()
        assert _parse_selection("", {1, 2}) == set()

    def test_invalid_part_ignored(self):
        assert _parse_selection("1,abc,3", {1, 2, 3}) == {1, 3}


class TestApplySkipFilters:
    ENTRIES = [
        {"title": "Normalny artykuł", "url": "https://example.com/a"},
        {"title": "SPONSOROWANE: kup teraz", "url": "https://example.com/b"},
        {"title": "Inny tekst", "url": "https://uw7.org/un/123"},
    ]

    def test_no_patterns_keeps_everything(self):
        kept, ignored = apply_skip_filters(self.ENTRIES, {})
        assert kept == self.ENTRIES
        assert ignored == []

    def test_url_prefix_filter(self):
        feed = {"skip_url_patterns": ["https://uw7.org/un"]}
        kept, ignored = apply_skip_filters(self.ENTRIES, feed)
        assert len(kept) == 2
        assert ignored[0]["url"] == "https://uw7.org/un/123"

    def test_title_regex_filter_case_insensitive(self):
        feed = {"skip_title_patterns": ["^sponsorowane"]}
        kept, ignored = apply_skip_filters(self.ENTRIES, feed)
        assert len(ignored) == 1
        assert ignored[0]["title"].startswith("SPONSOROWANE")

    def test_kept_plus_ignored_covers_all(self):
        feed = {"skip_url_patterns": ["https://uw7.org/un"],
                "skip_title_patterns": ["^sponsorowane"]}
        kept, ignored = apply_skip_filters(self.ENTRIES, feed)
        assert len(kept) + len(ignored) == len(self.ENTRIES)


class TestDetectDocumentType:
    @pytest.mark.parametrize("url", [
        "https://www.youtube.com/watch?v=abc123",
        "https://youtu.be/abc123",
        "https://m.youtube.com/watch?v=abc123",
    ])
    def test_youtube_urls(self, url):
        assert detect_document_type(url) == "youtube"

    def test_regular_link(self):
        assert detect_document_type("https://example.com/artykul") == "link"

    def test_youtube_in_path_is_not_youtube(self):
        assert detect_document_type("https://example.com/youtube.com") == "link"


class TestResolveDefaultState:
    def test_configured_state_wins(self):
        assert resolve_default_state({"default_state": "READY_FOR_EMBEDDING"}) == "READY_FOR_EMBEDDING"

    def test_default_is_url_added(self):
        assert resolve_default_state({}) == "URL_ADDED"


class TestBuildFeedUrl:
    def test_youtube_channel(self):
        feed = {"type": "youtube_channel", "channel_id": "UCabc"}
        assert build_feed_url(feed) == "https://www.youtube.com/feeds/videos.xml?channel_id=UCabc"

    @pytest.mark.parametrize("feed_type", ["wordpress", "rss", "json_api"])
    def test_url_feeds(self, feed_type):
        feed = {"type": feed_type, "url": "https://example.com/feed"}
        assert build_feed_url(feed) == "https://example.com/feed"

    def test_unknown_type_raises(self):
        with pytest.raises(ValueError):
            build_feed_url({"type": "carrier_pigeon"})
