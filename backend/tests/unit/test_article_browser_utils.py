"""Unit tests for pure helper functions in imports.article_browser.

article_browser imports DB modules and calls load_config() at module level.
In the lightweight uvx pytest environment those are unavailable, so minimal
stubs are injected into sys.modules just for the import of the module under
test, then removed — other test modules (which use pytest.importorskip on the
real packages) are unaffected. In a full venv the real modules are used. The
tested functions never touch the stubbed modules.
"""

import importlib
import sys
import types

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
_ensure_importable("library.db.models", WebDocument=type("WebDocument", (), {}))

try:
    from imports.article_browser import _article_full_text, _trim_to_sentences
finally:
    _remove_stubs()


class TestTrimToSentences:
    def test_short_text_unchanged(self):
        assert _trim_to_sentences("Krótki tekst.", 100, from_end=False) == "Krótki tekst."

    def test_trim_from_start_ends_on_sentence(self):
        text = "Pierwsze zdanie jest tutaj. Drugie zdanie jest dłuższe. Trzecie zdanie na koniec."
        result = _trim_to_sentences(text, 40, from_end=False)
        assert result.endswith("…")
        # Przycięte do granicy zdania (kropka przed wielokropkiem)
        assert result.rstrip("…").rstrip().endswith(".")

    def test_trim_from_end_starts_on_sentence(self):
        text = "Pierwsze zdanie jest tutaj. Drugie zdanie jest dłuższe. Trzecie zdanie na koniec."
        result = _trim_to_sentences(text, 40, from_end=True)
        assert result.startswith("…")
        assert "Trzecie zdanie na koniec." in result

    def test_no_sentence_boundary_falls_back_to_hard_cut(self):
        text = "a" * 200
        result = _trim_to_sentences(text, 50, from_end=False)
        assert result == "a" * 50 + "…"
        result_end = _trim_to_sentences(text, 50, from_end=True)
        assert result_end == "…" + "a" * 50

    def test_strips_whitespace_first(self):
        assert _trim_to_sentences("  tekst  ", 100, from_end=False) == "tekst"


class TestArticleFullText:
    def test_text_only(self):
        article = {"text": "Treść artykułu.", "links": [], "images": []}
        assert _article_full_text(article) == "Treść artykułu."

    def test_links_appended_with_markers(self):
        article = {
            "text": "Treść.",
            "links": [{"text": "Przykład", "url": "https://example.com"}],
            "images": [],
        }
        result = _article_full_text(article)
        assert "## Linki w artykule" in result
        assert "[link0] Przykład — https://example.com" in result

    def test_images_appended_with_alt(self):
        article = {
            "text": "Treść.",
            "links": [],
            "images": [{"alt": "Opis", "url": "https://example.com/img.jpg"}],
        }
        result = _article_full_text(article)
        assert "## Obrazki w artykule" in result
        assert "[img0] — Opis — https://example.com/img.jpg" in result

    def test_image_without_alt(self):
        article = {
            "text": "Treść.",
            "links": [],
            "images": [{"url": "https://example.com/img.jpg"}],
        }
        result = _article_full_text(article)
        assert "[img0] — https://example.com/img.jpg" in result
