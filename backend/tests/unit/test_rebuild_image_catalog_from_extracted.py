"""Unit tests for the single-document image catalog pilot (no database)."""

import logging
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

pytest.importorskip("sqlalchemy")

from imports import rebuild_image_catalog_from_extracted as backfill  # noqa: E402


@pytest.fixture
def pilot(monkeypatch):
    doc = SimpleNamespace(
        id=10482, title="Pilot", document_type="webpage",
        text_md="Keep [img0: Chart] and [img1] exactly.",
        text_extracted="Original ![Chart](https://example.com/chart.png) and ![](https://example.com/photo.jpg)",
    )
    session = MagicMock()
    session.get.return_value = doc
    queries = {model: MagicMock() for model in (
        backfill.DocumentImage, backfill.DocumentAnalysisRun, backfill.DocumentChunk, backfill.DocumentEmbedding,
    )}
    for query in queries.values():
        query.filter.return_value.count.return_value = 0
    session.query.side_effect = queries.__getitem__
    replace = MagicMock(return_value=[object(), object()])
    monkeypatch.setattr(backfill, "load_config", MagicMock())
    monkeypatch.setattr(backfill, "get_session", lambda: session)
    monkeypatch.setattr(backfill, "replace_document_images", replace)
    monkeypatch.setattr("sys.argv", ["backfill", "--id", "10482", "--apply"])
    return doc, session, queries, replace


def assert_no_writes(session, replace):
    replace.assert_not_called()
    session.commit.assert_not_called()
    session.execute.assert_not_called()
    session.add_all.assert_not_called()
    session.close.assert_called_once()


@pytest.mark.parametrize("kind", ["missing", "type", "empty", "none", "images", "run", "chunk", "embedding"])
def test_refused(pilot, kind, caplog):
    doc, session, queries, replace = pilot
    if kind == "missing":
        session.get.return_value = None
    elif kind == "type":
        doc.document_type = "obsidian_note"
    elif kind in ("empty", "none"):
        doc.text_extracted = "" if kind == "empty" else None
    else:
        model = {
            "images": backfill.DocumentImage, "run": backfill.DocumentAnalysisRun,
            "chunk": backfill.DocumentChunk, "embedding": backfill.DocumentEmbedding,
        }[kind]
        queries[model].filter.return_value.count.return_value = 1
    before = vars(doc).copy()
    assert backfill.main() == 1
    assert "refusing" in caplog.text
    assert vars(doc) == before
    assert_no_writes(session, replace)


@pytest.mark.parametrize("document_type", ["webpage", "link"])
def test_apply(pilot, document_type):
    doc, session, queries, replace = pilot
    doc.document_type = document_type
    before = vars(doc).copy()
    assert backfill.main() == 0
    replace.assert_called_once_with(session, doc.id, [
        {"alt": "Chart", "url": "https://example.com/chart.png"},
        {"alt": "", "url": "https://example.com/photo.jpg"},
    ])
    session.commit.assert_called_once_with()
    session.close.assert_called_once_with()
    assert vars(doc) == before
    session.get.assert_called_once_with(backfill.Document, doc.id)
    for model, query in queries.items():
        filters = query.filter.call_args.args
        assert filters[0].compare(model.document_id == doc.id)
        if model is backfill.DocumentImage:
            assert len(filters) == 2
            assert filters[1].compare(model.storage_key.is_(None))
        else:
            assert len(filters) == 1
        query.filter.return_value.count.assert_called_once_with()


def test_dry_run(pilot, monkeypatch, caplog):
    doc, session, _, replace = pilot
    monkeypatch.setattr("sys.argv", ["backfill", "--id", str(doc.id)])
    before = vars(doc).copy()
    with caplog.at_level(logging.INFO):
        assert backfill.main() == 0
    assert_no_writes(session, replace)
    assert vars(doc) == before
    for expected in ("Dry-run", "Pilot", str(len(doc.text_extracted)), "2 image(s)",
                     "https://example.com/chart.png", "alt='Chart'", "https://example.com/photo.jpg",
                     "alt=''", "count (storage_key IS NULL): 0", "text_md/text_extracted will NOT be modified"):
        assert expected in caplog.text


def test_no_images(pilot, caplog):
    doc, session, _, replace = pilot
    doc.text_extracted = "Plain text without images."
    with caplog.at_level(logging.INFO):
        assert backfill.main() == 0
    assert "no images found in text_extracted, nothing to do" in caplog.text
    assert_no_writes(session, replace)
