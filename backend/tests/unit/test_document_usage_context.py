"""Offline document attribution through real orchestrators and LLM leaves."""
import ast
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from flask import Flask, jsonify, request

from library.db.models import Document, DocumentEntity
from library.llm_usage.context import current_usage_context, llm_usage_context


@pytest.fixture
def calls(monkeypatch):
    seen = []

    def ask(*args, **kwargs):
        seen.append((kwargs["operation"], current_usage_context()))
        return SimpleNamespace(response_text="BRAK", usage=None)

    monkeypatch.setattr("library.ai.ai_ask", ask)
    monkeypatch.setattr("library.article_tagging._tagging_model", lambda: "test-model")
    return seen


def test_apply_tags(calls):
    from library.document_analysis_service import _apply_tags

    with llm_usage_context(analysis_job_id="job", analysis_run_id=91):
        _apply_tags(SimpleNamespace(id=42, title="Title", tags=""), "Neutral text.")
        assert current_usage_context() == (None, "job", 91)
    assert ("thematic_tagging", (42, "job", 91)) in calls


@pytest.mark.parametrize("outer_document", [None, 42, 99])
def test_person_resolution(calls, monkeypatch, outer_document):
    from library.person_registry import resolve_document_persons

    session = MagicMock()
    session.query.return_value.filter.return_value.all.return_value = [DocumentEntity(entity_text="Tusk")]
    monkeypatch.setattr("library.wikidata_client.search_persons", lambda name: [
        {"qid": "Q1", "label": "Donald Tusk", "description": "politician"}])
    with llm_usage_context(document_id=outer_document, analysis_job_id="job", analysis_run_id=91):
        resolve_document_persons(session, SimpleNamespace(id=42, title="Title"), "Tusk spoke.")
        assert current_usage_context() == (outer_document, "job", 91)
    assert calls == [("place_candidate_selection", (42, "job", 91))]


def test_place_resolution(calls, monkeypatch):
    from library.place_verification import verify_document_places

    entity = DocumentEntity(entity_text="Paris", entity_type="placeName", source="ner", mention_count=1,
                            variants=[], geocode_id=1)
    entity.geocode = None
    # A resolved cache entry avoids network geocoding; relevance still uses the real LLM leaf.
    from library.db.models import GeocodeCache
    entity.geocode = GeocodeCache(id=1, resolved=True, display_name="Paris", query="Paris")
    session = MagicMock()
    session.query.return_value.filter.return_value.all.return_value = [entity]
    monkeypatch.setattr("library.place_verification._canonicalize_and_merge_places", lambda s, rows: rows)
    monkeypatch.setattr("library.place_context_classifier.classify_place_context_candidates", lambda *a: [])
    with llm_usage_context(analysis_job_id="job", analysis_run_id=91):
        verify_document_places(session, SimpleNamespace(id=42, title="Title", tags=""), "Paris is a city.")
        assert current_usage_context() == (None, "job", 91)
    assert ("place_relevance", (42, "job", 91)) in calls


def test_entity_refresh_alias_resolution(calls, monkeypatch):
    from library import entity_service as service
    from tests.unit.test_entity_service import _session_with_exclusions

    session = _session_with_exclusions([])
    session.get.return_value = SimpleNamespace(id=42, title="Title", byline=None, ner_unavailable_at=None)
    monkeypatch.setattr(service, "_apply_channel_glossary", lambda s, d, text: (text, []))
    monkeypatch.setattr(service, "extract_entities", lambda text: [
        {"text": "Congress", "label": "orgName", "lemma": "Congress"}])
    monkeypatch.setattr(service, "ambiguous_alias_candidates_for_forms", lambda *a: ("Congress", [
        SimpleNamespace(id=1, organization=SimpleNamespace(canonical_name="Congress A"), context_hint="A"),
        SimpleNamespace(id=2, organization=SimpleNamespace(canonical_name="Congress B"), context_hint="B")]))
    with llm_usage_context(analysis_job_id="job", analysis_run_id=91):
        service.refresh_document_entities(session, 42, "Congress spoke.")
        assert current_usage_context() == (None, "job", 91)
    assert ("organization_alias_context_resolution", (42, "job", 91)) in calls


def _server_handler(name, session):
    # Execute the real handler without importing server's deployment configuration.
    path = Path(__file__).parents[2] / "server.py"
    node = next(n for n in ast.parse(path.read_text(encoding="utf-8")).body
                if isinstance(n, ast.FunctionDef) and n.name == name)
    node.decorator_list = []
    namespace = {"get_scoped_session": lambda: session, "Document": Document,
                 "jsonify": jsonify, "request": request}
    exec(compile(ast.Module(body=[node], type_ignores=[]), str(path), "exec"), namespace)
    return namespace[name]


@pytest.mark.parametrize("kind,arena", [("eventName", False), ("orgName", False), ("orgName", True)])
def test_description_handlers(calls, monkeypatch, kind, arena):
    session = MagicMock()
    entity = SimpleNamespace(document_id=42, entity_type=kind, entity_text="EDF", variants=[])
    doc = SimpleNamespace(text_md=None, text="## Energy\n\nEDF operates power stations.", title="Title")
    session.get.side_effect = lambda model, key: entity if model is DocumentEntity else doc
    monkeypatch.setattr("library.llm_model_registry.selectable_models", lambda: [
        {"id": "one", "label": "One"}, {"id": "two", "label": "Two"}])
    handler = _server_handler("website_entities_describe_arena" if arena else "website_entities_describe", session)
    app = Flask(__name__)
    with app.test_request_context(json={"models": ["one", "two"]} if arena else {}):
        with llm_usage_context(analysis_job_id="job", analysis_run_id=91):
            assert handler(7)[1] == 200
            assert current_usage_context() == (None, "job", 91)
    operation = "event_description" if kind == "eventName" else "organization_description"
    assert calls == [(operation, (42, "job", 91))] * (2 if arena else 1)


def test_search_terms_handler(calls):
    session = MagicMock()
    session.get.return_value = SimpleNamespace(id=42, title="Title", text="Text", text_md=None, search_terms="")
    handler = _server_handler("generate_document_search_terms", session)
    with Flask(__name__).test_request_context(json={}):
        with llm_usage_context(analysis_job_id="job", analysis_run_id=91):
            assert handler(42)[1] == 200
            assert current_usage_context() == (None, "job", 91)
    assert calls == [("search_terms_generation", (42, "job", 91))]
