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
