"""Unit tests for GET /document/<id>/readiness — the reader's
"Stan przetwarzania" checklist (library/chunk_review_routes.py).

The endpoint is read-only: every step is derived from a column/row that
already exists (text, analysis run + chunk statuses, document_embeddings,
entities_checked_at, enrichment_run_at, quality, tags, obsidian_note_paths).
Which steps count toward the "gotowy" verdict depends on document_type.
"""

import datetime
from unittest.mock import MagicMock

import pytest

pytest.importorskip("sqlalchemy")
flask = pytest.importorskip("flask")

from library import chunk_review_routes as cr  # noqa: E402
from library.db.models import Document  # noqa: E402

LONG_TEXT = "Treść artykułu wystarczająco długa, by _extract_text uznał ją za użyteczną. " * 4


def _make_doc(**overrides) -> Document:
    doc = MagicMock(spec=Document)
    doc.id = overrides.get("id", 10455)
    doc.document_type = overrides.get("document_type", "webpage")
    doc.text = None
    doc.text_md = overrides.get("text_md", LONG_TEXT)
    doc.text_raw = None
    doc.tags = overrides.get("tags", "")
    doc.quality = overrides.get("quality", None)
    doc.entities_checked_at = overrides.get("entities_checked_at", None)
    doc.ner_unavailable_at = overrides.get("ner_unavailable_at", None)
    doc.enrichment_run_at = overrides.get("enrichment_run_at", None)
    doc.obsidian_note_paths = overrides.get("obsidian_note_paths", [])
    return doc


def _client(monkeypatch, doc, *, run=None, scalars=(0, 0, 0)):
    session = MagicMock()
    session.get.side_effect = lambda model, pk: doc if model is Document and pk == doc.id else None
    session.scalar.side_effect = list(scalars)
    monkeypatch.setattr(cr, "get_scoped_session", lambda: session)
    monkeypatch.setattr(cr, "_latest_run_for_document", lambda _s, _d: run)
    app = flask.Flask(__name__)
    app.register_blueprint(cr.bp)
    return app.test_client()


def _step(body, key):
    return next(s for s in body["steps"] if s["key"] == key)


class TestFreshWebpage:
    def test_nothing_done_yet_needs_work(self, monkeypatch):
        client = _client(monkeypatch, _make_doc(), run=None, scalars=[0])

        body = client.get("/document/10455/readiness").get_json()

        assert body["status"] == "success"
        assert body["verdict"] == "needs_work"
        assert body["required_total"] == 7
        assert body["required_done"] == 1  # only "content"
        assert _step(body, "content")["state"] == "done"
        assert _step(body, "chunks")["state"] == "todo"
        assert _step(body, "chunks")["link"] == "/chunks/10455"
        assert _step(body, "embeddings")["state"] == "todo"
        assert _step(body, "ner")["state"] == "todo"
        assert _step(body, "enrichment")["state"] == "todo"
        assert _step(body, "quality")["state"] == "todo"
        assert _step(body, "tags")["state"] == "todo"
        assert _step(body, "obsidian_note")["required"] is False


class TestFullyProcessedWebpage:
    def test_all_required_steps_done_is_ready(self, monkeypatch):
        run = MagicMock(id=7, status="reviewed")
        doc = _make_doc(
            tags="geopolityka, kraj-usa, miejsce-kijow",
            quality={"score": 82},
            entities_checked_at=datetime.datetime(2026, 8, 20, 10, 0),
            enrichment_run_at=datetime.datetime(2026, 8, 21, 9, 0),
            obsidian_note_paths=["02-wiedza/Geopolityka i polityka/nota.md"],
        )
        # scalar calls: run_total, run_pending, embeddings_count
        client = _client(monkeypatch, doc, run=run, scalars=[12, 0, 40])

        body = client.get("/document/10455/readiness").get_json()

        assert body["verdict"] == "ready"
        assert body["required_done"] == body["required_total"] == 7
        assert _step(body, "chunks")["state"] == "done"
        assert _step(body, "embeddings")["state"] == "done"
        assert _step(body, "tags")["detail"] == "geopolityka"
        assert _step(body, "obsidian_note")["state"] == "done"


class TestOpenReview:
    def test_run_with_pending_chunks_is_partial_not_done(self, monkeypatch):
        run = MagicMock(id=7, status="in_review")
        client = _client(monkeypatch, _make_doc(), run=run, scalars=[12, 5, 0])

        body = client.get("/document/10455/readiness").get_json()

        assert _step(body, "chunks")["state"] == "partial"
        assert body["verdict"] == "needs_work"


class TestObsidianNote:
    def test_chunks_enrichment_quality_are_not_applicable(self, monkeypatch):
        doc = _make_doc(document_type="obsidian_note", tags="wiedza")
        client = _client(monkeypatch, doc, run=None, scalars=[0])

        body = client.get("/document/10455/readiness").get_json()

        assert _step(body, "chunks")["state"] == "na"
        assert _step(body, "enrichment")["state"] == "na"
        assert _step(body, "quality")["state"] == "na"
        assert _step(body, "obsidian_note")["state"] == "na"
        assert body["required_total"] == 4  # content, embeddings, ner, tags


class TestMissingDocument:
    def test_unknown_id_returns_404(self, monkeypatch):
        client = _client(monkeypatch, _make_doc(), run=None, scalars=[0])

        assert client.get("/document/999999/readiness").status_code == 404
