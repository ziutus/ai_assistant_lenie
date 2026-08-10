"""refresh_document_enrichment(): trailing author-biography isolation before NER.

See doc 9373 (Kamila Gurgul / Wiadomości WP) — a trailing "o autorze" widget
was flowing into entities/places/persons unstripped, unlike the equivalent
step in document_analysis_service.create_run().
"""

from types import SimpleNamespace
from unittest.mock import MagicMock

from library.document_enrichment import refresh_document_enrichment

ARTICLE_BODY = ("Treść artykułu. " * 80) + "\n\n## Rozdział\n\nDalsza treść."
BIO = (
    "Kamila Gurgul dziennikarką jest od 2020 roku. Zajmuje się bieżącymi "
    "wydarzeniami w kraju i pisze dla Wiadomości WP."
)


def _session() -> MagicMock:
    return MagicMock()


def _patch_stages(monkeypatch, calls: dict):
    monkeypatch.setattr(
        "library.entity_service.refresh_document_entities",
        lambda session, doc_id, text: calls.setdefault("entities", []).append(text) or [],
    )
    monkeypatch.setattr(
        "library.place_verification.verify_document_places",
        lambda session, doc, text: calls.setdefault("places", []).append(text)
        or {"resolved": [], "tagged": []},
    )
    monkeypatch.setattr(
        "library.person_registry.resolve_document_persons",
        lambda session, doc, text: calls.setdefault("persons", []).append(text)
        or {"linked": [], "skipped": []},
    )
    monkeypatch.setattr(
        "library.timeline_events.refresh_document_events",
        lambda session, doc, model: {"events": []},
    )
    monkeypatch.setattr(
        "library.time_periods.refresh_document_periods",
        lambda session, doc, model: {"periods": []},
    )
    monkeypatch.setattr(
        "library.tones.refresh_document_tones",
        lambda session, doc, model: {"tones": []},
    )
    monkeypatch.setattr(
        "library.information_provenance.refresh_document_information_sources",
        lambda session, doc, text, model: {"sources": []},
    )
    monkeypatch.setattr(
        "library.control_question_selection.refresh_document_control_answers",
        lambda session, doc, model: {"answers": []},
    )


def test_trailing_author_bio_stripped_before_entity_stages(monkeypatch):
    doc = SimpleNamespace(
        id=9373, byline="Kamila Gurgul", text_md=ARTICLE_BODY + "\n\n" + BIO,
        text=None, text_raw=None,
    )
    session = _session()
    calls: dict = {}
    _patch_stages(monkeypatch, calls)

    bio_calls = []
    monkeypatch.setattr(
        "library.author_biography.process_author_biography",
        lambda _session, _doc, bio, _model: bio_calls.append(bio)
        or {"person_id": 1, "status": "auto_applied"},
    )

    results = refresh_document_enrichment(session, doc, "test-model")

    assert calls["entities"] == [ARTICLE_BODY]
    assert calls["places"] == [ARTICLE_BODY]
    assert calls["persons"] == [ARTICLE_BODY]
    assert bio_calls == [BIO]
    assert doc.text_md == ARTICLE_BODY
    assert results["author_biography"] == {"person_id": 1, "status": "auto_applied"}
    assert not results["errors"]


def test_no_bio_detected_leaves_text_untouched(monkeypatch):
    doc = SimpleNamespace(
        id=9374, byline="Kamila Gurgul", text_md=ARTICLE_BODY, text=None, text_raw=None,
    )
    session = _session()
    calls: dict = {}
    _patch_stages(monkeypatch, calls)
    bio_calls = []
    monkeypatch.setattr(
        "library.author_biography.process_author_biography",
        lambda *a, **kw: bio_calls.append(a) or {"person_id": 1, "status": "auto_applied"},
    )

    results = refresh_document_enrichment(session, doc, "test-model")

    assert calls["entities"] == [ARTICLE_BODY]
    assert bio_calls == []
    assert doc.text_md == ARTICLE_BODY
    assert "author_biography" not in results


def test_no_byline_skips_bio_extraction_entirely(monkeypatch):
    full_text = ARTICLE_BODY + "\n\n" + BIO
    doc = SimpleNamespace(id=9375, byline=None, text_md=full_text, text=None, text_raw=None)
    session = _session()
    calls: dict = {}
    _patch_stages(monkeypatch, calls)
    bio_calls = []
    monkeypatch.setattr(
        "library.author_biography.process_author_biography",
        lambda *a, **kw: bio_calls.append(a) or {"person_id": 1, "status": "auto_applied"},
    )

    results = refresh_document_enrichment(session, doc, "test-model")

    assert calls["entities"] == [full_text]
    assert bio_calls == []
    assert doc.text_md == full_text
    assert "author_biography" not in results


def test_reuse_existing_entities_skips_bio_extraction(monkeypatch):
    full_text = ARTICLE_BODY + "\n\n" + BIO
    doc = SimpleNamespace(id=9376, byline="Kamila Gurgul", text_md=full_text, text=None, text_raw=None)
    session = _session()
    calls: dict = {}
    _patch_stages(monkeypatch, calls)
    bio_calls = []
    monkeypatch.setattr(
        "library.author_biography.process_author_biography",
        lambda *a, **kw: bio_calls.append(a) or {"person_id": 1, "status": "auto_applied"},
    )

    results = refresh_document_enrichment(
        session, doc, "test-model", reuse_existing_entities=True,
    )

    assert "entities" not in calls
    assert bio_calls == []
    assert doc.text_md == full_text
    assert results["entities"] == {"reused": True}
