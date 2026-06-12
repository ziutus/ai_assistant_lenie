"""Unit tests for library.article_pipeline — shared step_1 markdown + LLM extraction pipeline.

article_pipeline imports its dependencies lazily. library.document_prepare pulls
markitdown/html2text (optional "markdown" extra), so a fake module is injected into
sys.modules instead of importing the real one. library.article_extractor is
stdlib-only at module level, so plain monkeypatch.setattr works. No DB, S3, or LLM
access happens.
"""

import sys
import types

import pytest

import library.article_pipeline as pipeline


class FakeDoc:
    def __init__(self, doc_id=123, url="https://example.com/artykul"):
        self.id = doc_id
        self.url = url


@pytest.fixture
def doc():
    return FakeDoc()


def _install_fake_document_prepare(monkeypatch, markdown_result):
    """Inject a fake library.document_prepare module; returns the list of recorded calls."""
    calls = []

    def fake_prepare(document_id, doc, cache_dir, verbose=False):
        calls.append(document_id)
        return markdown_result

    fake_module = types.ModuleType("library.document_prepare")
    fake_module.prepare_markdown = fake_prepare
    fake_module.save_document_info = lambda *a, **kw: None
    monkeypatch.setitem(sys.modules, "library.document_prepare", fake_module)
    return calls


@pytest.fixture
def prepare_calls(monkeypatch):
    """Fake document_prepare: records prepare_markdown calls, returns 'RAW MD'."""
    return _install_fake_document_prepare(monkeypatch, "RAW MD")


@pytest.fixture
def prepare_fails(monkeypatch):
    """Fake document_prepare: prepare_markdown returns None (fetch failure)."""
    return _install_fake_document_prepare(monkeypatch, None)


class TestEnsureRawMarkdown:
    def test_cache_hit_reads_step1_without_fetching(self, tmp_path, doc, prepare_calls):
        step1 = tmp_path / f"{doc.id}_step_1_all.md"
        step1.write_text("CACHED MD", encoding="utf-8")

        result = pipeline.ensure_raw_markdown(doc, str(tmp_path))

        assert result == "CACHED MD"
        assert prepare_calls == []  # nie pobierał z S3

    def test_cache_miss_fetches_and_persists_step1(self, tmp_path, doc, prepare_calls):
        result = pipeline.ensure_raw_markdown(doc, str(tmp_path))

        assert result == "RAW MD"
        assert prepare_calls == [doc.id]
        step1 = tmp_path / f"{doc.id}_step_1_all.md"
        assert step1.read_text(encoding="utf-8") == "RAW MD"

    def test_fetch_failure_returns_none_without_step1(self, tmp_path, doc, prepare_fails):
        result = pipeline.ensure_raw_markdown(doc, str(tmp_path))

        assert result is None
        assert not (tmp_path / f"{doc.id}_step_1_all.md").exists()

    def test_creates_cache_dir_when_missing(self, tmp_path, doc, prepare_calls):
        cache_dir = tmp_path / "markdown" / str(doc.id)

        result = pipeline.ensure_raw_markdown(doc, str(cache_dir))

        assert result == "RAW MD"
        assert cache_dir.is_dir()


class TestExtractArticle:
    def test_full_success(self, tmp_path, doc, prepare_calls, monkeypatch):
        llm_calls = []

        def fake_llm(markdown_text, document_id, cache_dir, url, **kw):
            llm_calls.append((markdown_text, document_id, url))
            return "ARTYKUŁ"

        monkeypatch.setattr("library.article_extractor.process_article_with_llm_fallback", fake_llm)

        markdown, article = pipeline.extract_article(doc, str(tmp_path))

        assert markdown == "RAW MD"
        assert article == "ARTYKUŁ"
        assert llm_calls == [("RAW MD", doc.id, doc.url)]

    def test_skip_llm_returns_markdown_only(self, tmp_path, doc, prepare_calls, monkeypatch):
        def fail_llm(*a, **kw):
            raise AssertionError("LLM nie powinien być wywołany przy skip_llm=True")

        monkeypatch.setattr("library.article_extractor.process_article_with_llm_fallback", fail_llm)

        markdown, article = pipeline.extract_article(doc, str(tmp_path), skip_llm=True)

        assert markdown == "RAW MD"
        assert article is None

    def test_markdown_failure_skips_llm(self, tmp_path, doc, prepare_fails, monkeypatch):
        def fail_llm(*a, **kw):
            raise AssertionError("LLM nie powinien być wywołany bez markdownu")

        monkeypatch.setattr("library.article_extractor.process_article_with_llm_fallback", fail_llm)

        markdown, article = pipeline.extract_article(doc, str(tmp_path))

        assert markdown is None
        assert article is None

    def test_llm_failure_returns_markdown_and_none(self, tmp_path, doc, prepare_calls, monkeypatch):
        monkeypatch.setattr("library.article_extractor.process_article_with_llm_fallback",
                            lambda *a, **kw: None)

        markdown, article = pipeline.extract_article(doc, str(tmp_path))

        assert markdown == "RAW MD"
        assert article is None
