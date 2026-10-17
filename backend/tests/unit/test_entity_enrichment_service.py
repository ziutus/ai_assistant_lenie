from sqlalchemy.exc import IntegrityError

from library.entity_enrichment_service import EntityEnrichmentCriticalError


def test_integrity_failure_requires_manual_intervention():
    error = IntegrityError("UPDATE document_entities", {}, RuntimeError("duplicate key"))

    critical = EntityEnrichmentCriticalError({"verify_places": error})

    assert critical.requires_manual_intervention is True
    assert critical.job_result(9394) == {
        "document_id": 9394,
        "failed_stages": ["verify_places"],
        "failure_kind": "integrity",
        "action": "manual_intervention",
    }


def test_transient_failure_is_retryable_before_manual_intervention():
    critical = EntityEnrichmentCriticalError({"resolve_persons": TimeoutError("Wikidata timeout")})

    assert critical.requires_manual_intervention is False
    assert critical.job_result(9394)["failure_kind"] == "transient"
    assert critical.job_result(9394)["action"] == "retry"


def test_chapter_types_invalidate_digest_and_queued_job():
    from types import SimpleNamespace
    from unittest.mock import MagicMock

    from library.entity_enrichment_service import _text_digest, execute_entity_enrichment

    doc = SimpleNamespace(text_md=None, text="## A\nJan.", chapter_types=["TEMAT"])
    digest = _text_digest(doc)
    job = SimpleNamespace(parameters={"document_id": 42, "text_digest": digest})
    doc.chapter_types = ["REKLAMA"]
    assert _text_digest(doc) != digest
    assert execute_entity_enrichment(MagicMock(get=MagicMock(return_value=doc)), job)["skipped"] == "document text changed"


def test_enrichment_uses_filtered_text(monkeypatch):
    from types import SimpleNamespace
    from unittest.mock import MagicMock

    from library.entity_enrichment_service import _text_digest, execute_entity_enrichment

    doc = SimpleNamespace(text_md=None, text="## A\nJan.\n\n## B\nSponsor.", chapter_types=["TEMAT", "REKLAMA"])
    session = MagicMock()
    session.get.return_value = doc
    monkeypatch.setattr("library.db.engine.get_session", lambda: session)
    monkeypatch.setattr("library.entity_enrichment_service.heartbeat", lambda *args: None)
    places = MagicMock(return_value={"tagged": []})
    persons = MagicMock(return_value={"linked": []})
    pipelines = MagicMock(return_value={"resolved": []})
    monkeypatch.setattr("library.place_verification.verify_document_places", places)
    monkeypatch.setattr("library.person_registry.resolve_document_persons", persons)
    monkeypatch.setattr("library.overpass_client.attach_document_pipelines", pipelines)
    job = SimpleNamespace(id="test", parameters={"document_id": 42, "text_digest": _text_digest(doc)})
    execute_entity_enrichment(session, job)
    assert places.call_args.args[2] == "## A\nJan."
    assert persons.call_args.args[2] == "## A\nJan."
    places.reset_mock()
    persons.reset_mock()
    pipelines.reset_mock()
    doc.chapter_types = ["SZUM", "REKLAMA"]
    job.parameters["text_digest"] = _text_digest(doc)
    assert execute_entity_enrichment(session, job)["skipped"] == "no NER text"
    places.assert_not_called()
    persons.assert_not_called()
    pipelines.assert_not_called()
