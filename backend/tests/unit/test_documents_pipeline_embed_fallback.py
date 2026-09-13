"""Focused tests for whole-document fallback embedding input."""

import importlib
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest


@pytest.mark.parametrize("text_field", ["text_md", "text"])
def test_webpage_embedding_strips_image_markers(monkeypatch, text_field):
    monkeypatch.setattr("library.config_loader.load_config", lambda: {})
    pipeline = importlib.import_module("documents_pipeline")
    original = "# Article\n\nBefore [img0]after.\n\n[img1: some caption]\n\nMore prose."
    doc = SimpleNamespace(id=77, document_type="webpage", language="en", text_md=None, text=None)
    setattr(doc, text_field, original)
    get_embedding = MagicMock(return_value=SimpleNamespace(status="success", embedding=[0.1]))
    monkeypatch.setattr("library.embedding.get_embedding", get_embedding)

    assert pipeline._embed_document_from_markdown(MagicMock(), MagicMock(), doc, "model")

    assert get_embedding.call_count > 0
    texts = [call.kwargs["text"] for call in get_embedding.call_args_list]
    assert all("[img" not in text for text in texts)
    assert "Before" in " ".join(texts)
    assert "More prose." in " ".join(texts)
    assert getattr(doc, text_field) == original
    assert getattr(doc, "text" if text_field == "text_md" else "text_md") is None
