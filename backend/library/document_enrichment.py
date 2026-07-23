"""Derived-document enrichment run after Markdown review and before search chunks."""

import logging
from collections.abc import Callable

from library.document_analysis_service import _extract_text

logger = logging.getLogger(__name__)


def refresh_document_enrichment(
    session,
    doc,
    model: str,
    progress_fn: Callable[[str], None] | None = None,
) -> dict:
    """Refresh whole-document derived data from the canonical cleaned text.

    Individual enrichers internally split long documents into chapters or
    model-sized fragments. Failures are isolated so one unavailable auxiliary
    service does not discard successful derived data from the other stages.
    """
    text, field = _extract_text(doc, prefer_md=True)
    if not text:
        raise ValueError(f"Document {doc.id} has no usable text")

    errors: dict[str, str] = {}
    results: dict[str, object] = {"source_field": field, "errors": errors}

    def progress(message: str) -> None:
        logger.info("enrichment doc=%s: %s", doc.id, message)
        if progress_fn:
            progress_fn(message)

    def run_stage(name: str, label: str, operation) -> None:
        progress(label)
        try:
            results[name] = operation()
            session.commit()
        except Exception as exc:
            session.rollback()
            logger.exception("enrichment stage %s failed for document %s", name, doc.id)
            errors[name] = str(exc)

    run_stage(
        "entities", "Wykrywanie osób i miejsc…",
        lambda: {"count": len(__import__(
            "library.entity_service", fromlist=["refresh_document_entities"],
        ).refresh_document_entities(session, doc.id, text))},
    )
    run_stage(
        "places", "Weryfikacja miejsc…",
        lambda: __import__(
            "library.place_verification", fromlist=["verify_document_places"],
        ).verify_document_places(session, doc, text),
    )
    run_stage(
        "persons", "Łączenie osób z rejestrem…",
        lambda: __import__(
            "library.person_registry", fromlist=["resolve_document_persons"],
        ).resolve_document_persons(session, doc, text),
    )
    run_stage(
        "events", "Budowanie osi czasu…",
        lambda: __import__(
            "library.timeline_events", fromlist=["refresh_document_events"],
        ).refresh_document_events(session, doc, model),
    )
    run_stage(
        "time_periods", "Rozpoznawanie okresów historycznych…",
        lambda: __import__(
            "library.time_periods", fromlist=["refresh_document_periods"],
        ).refresh_document_periods(session, doc, model),
    )
    run_stage(
        "tones", "Analiza tonu i emocji…",
        lambda: __import__(
            "library.tones", fromlist=["refresh_document_tones"],
        ).refresh_document_tones(session, doc, model),
    )
    run_stage(
        "information_sources", "Analiza źródeł informacji…",
        lambda: __import__(
            "library.information_provenance", fromlist=["refresh_document_information_sources"],
        ).refresh_document_information_sources(session, doc, text, model),
    )
    progress("Wzbogacanie dokumentu zakończone")
    return results
