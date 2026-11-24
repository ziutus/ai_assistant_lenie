"""Shared unit-test fixtures."""

import pytest


@pytest.fixture(autouse=True)
def no_org_context_model_in_service_tests(request, monkeypatch):
    """Service unit tests opt into organization model calls explicitly."""
    if (request.module.__name__.endswith("test_org_context_classifier")
            or request.node.name == "test_common_noun_org_is_dropped_before_registry_creation"):
        return
    from library import org_context_classifier

    monkeypatch.setattr(org_context_classifier, "classify_suspicious_org_candidates", lambda *args, **kwargs: [])


@pytest.fixture(autouse=True)
def no_database_gazetteer_entries(monkeypatch):
    """Keep unit tests off the database: the NER gazetteer store returns no extra entries.

    Without this the store would open a real session (and read Vault config) the first time
    any gazetteer is consulted. Tests of the store itself patch ``_fetch_rows`` again.
    """
    try:
        from library import ner_gazetteer_store
    except ImportError:  # lightweight env without optional dependencies
        yield
        return
    monkeypatch.setattr(ner_gazetteer_store, "_fetch_rows", lambda: [])
    ner_gazetteer_store.invalidate_cache()
    yield
    ner_gazetteer_store.invalidate_cache()


def _database_unavailable():
    raise RuntimeError("no database in unit tests")


@pytest.fixture(autouse=True)
def no_database_llm_models(monkeypatch):
    """Keep unit tests off the database: the model allowlist falls back to the code seed (ADR-032).

    Tests of the store or of registry behaviour on database rows patch ``_fetch_rows`` / ``get_models`` again.
    """
    try:
        from library import llm_model_store
    except ImportError:  # lightweight env without optional dependencies
        yield
        return
    monkeypatch.setattr(llm_model_store, "_fetch_rows", _database_unavailable)
    llm_model_store.invalidate_cache()
    yield
    llm_model_store.invalidate_cache()


@pytest.fixture
def all_provider_models(monkeypatch):
    """A model list that offers direct OpenAI and Google Vertex models again.

    The production allowlist keeps only OpenRouter and CloudFerro visible (migration f6b1a9c4d7e2 retires the others),
    but the registry's provider rules (JSON-schema support, prices from ``llm_pricing``, availability) are still tested
    against those providers: this gives such a test its own list instead of tying it to what the seed hides.
    """
    from dataclasses import replace

    from library import llm_model_store

    models = tuple(
        replace(m, status="active") if m.provider in ("openai", "google-vertexai") else m
        for m in llm_model_store.SEED_MODELS
    )
    monkeypatch.setattr(llm_model_store, "get_models", lambda: models)
    return models
