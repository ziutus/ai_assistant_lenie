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
