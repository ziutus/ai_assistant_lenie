"""Shared unit-test fixtures."""

import pytest


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
