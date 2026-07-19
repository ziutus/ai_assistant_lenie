"""Unit tests for clean_onet_artifacts() extracted from document_md_decode.py.

md_decode imports DB/LLM/markdown modules at module level. In the lightweight
uvx pytest environment those are unavailable, so minimal stubs are injected
into sys.modules just for the import of the module under test, then removed —
other test modules (which use pytest.importorskip on the real packages) are
unaffected. In a full venv the real modules are used. The tested function
never touches the stubbed modules.
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


_ensure_importable("library.api.cloudferro.sherlock.sherlock_embedding",
                   sherlock_create_embeddings=lambda *a, **kw: None)
_ensure_importable("library.document_prepare",
                   calculate_reduction=lambda h, m: ((h - m) / h) * 100)
_ensure_importable("library.config_loader",
                   load_config=lambda: types.SimpleNamespace(
                       get=lambda *a, **kw: None, require=lambda *a, **kw: ""))
_ensure_importable("library.db.engine", get_session=lambda: None)
_ensure_importable("library.db.models", Document=type("Document", (), {}))
_ensure_importable("library.document_repository",
                   DocumentRepository=type("DocumentRepository", (), {}))

try:
    from document_md_decode import clean_onet_artifacts
finally:
    _remove_stubs()


class TestCleanOnetArtifacts:
    def test_czytaj_wiecej_removed(self):
        text = "Akapit treści.\n**CZYTAJ WIĘCEJ: kolejny artykuł**\nDalsza treść."
        result = clean_onet_artifacts(text)
        assert "CZYTAJ WIĘCEJ" not in result
        assert "Akapit treści." in result
        assert "Dalsza treść." in result

    def test_zobacz_takze_bullet_removed(self):
        text = "Treść.\n * **Zobacz także:** inny tekst\nKoniec."
        result = clean_onet_artifacts(text)
        assert "Zobacz także" not in result
        assert "Koniec." in result

    def test_przeczytaj_takze_bullet_removed(self):
        text = "Treść.\n * **Przeczytaj także:** inny tekst\nKoniec."
        result = clean_onet_artifacts(text)
        assert "Przeczytaj także" not in result

    def test_reklama_line_removed(self):
        text = "Akapit pierwszy.\nreklama\nAkapit drugi."
        result = clean_onet_artifacts(text)
        assert "reklama" not in result
        assert "Akapit pierwszy." in result
        assert "Akapit drugi." in result

    def test_trailing_reklama_removed(self):
        text = "Treść artykułu.\n  reklama"
        result = clean_onet_artifacts(text)
        assert result.rstrip().endswith("Treść artykułu.")

    def test_dalszy_ciag_pod_wideo_removed(self):
        text = "Przed.\nDalszy ciąg materiału pod wideo\nPo."
        result = clean_onet_artifacts(text)
        assert "Dalszy ciąg" not in result

    def test_blank_line_inserted_before_header(self):
        text = "Akapit.\n## Nagłówek sekcji"
        result = clean_onet_artifacts(text)
        assert "Akapit.\n\n## Nagłówek sekcji" in result

    def test_plain_text_preserved(self):
        text = "Pierwszy akapit artykułu.\n\nDrugi akapit z https://example.com w treści."
        result = clean_onet_artifacts(text)
        assert "Pierwszy akapit artykułu." in result
        assert "Drugi akapit z https://example.com w treści." in result
