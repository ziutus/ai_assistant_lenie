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
    reuse_existing_entities: bool = False,
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

    if reuse_existing_entities:
        progress("Wykorzystuję wcześniejsze osoby i miejsca…")
        results["entities"] = {"reused": True}
        results["places"] = {"reused": True}
        results["persons"] = {"reused": True}
    else:
        # A trailing "o autorze" widget (byline + bio paragraph) pollutes NER
        # with the author's employer/alma mater as if they were discussed in
        # the article. document_analysis_service.create_run() isolates this
        # into its own SZUM chunk for review, but never strips it before its
        # own entity extraction either — do it here so the person/place stages
        # only see the actual article body. Persisted back to the source field
        # so later runs (and the reader) don't see it again.
        entity_text = text
        author_bio = None
        author = (getattr(doc, "byline", None) or "").strip()
        if author:
            from library.author_biography import extract_trailing_author_biography

            stripped_text, author_bio = extract_trailing_author_biography(text, author)
            if author_bio:
                entity_text = stripped_text
                progress("Wydzielam notkę biograficzną autora…")
                if field in ("text_md", "text"):
                    setattr(doc, field, stripped_text)
                    session.commit()

        run_stage(
            "entities", "Wykrywanie osób i miejsc…",
            lambda: {"count": len(__import__(
                "library.entity_service", fromlist=["refresh_document_entities"],
            ).refresh_document_entities(session, doc.id, entity_text))},
        )
        run_stage(
            "places", "Weryfikacja miejsc…",
            lambda: __import__(
                "library.place_verification", fromlist=["verify_document_places"],
            ).verify_document_places(session, doc, entity_text),
        )
        run_stage(
            "persons", "Łączenie osób z rejestrem…",
            lambda: __import__(
                "library.person_registry", fromlist=["resolve_document_persons"],
            ).resolve_document_persons(session, doc, entity_text),
        )
        if author_bio:
            run_stage(
                "author_biography", "Przetwarzanie notki biograficznej autora…",
                lambda: __import__(
                    "library.author_biography", fromlist=["process_author_biography"],
                ).process_author_biography(session, doc, author_bio, model),
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
    run_stage(
        "control_questions", "Dobór pytań kontrolnych…",
        lambda: __import__(
            "library.control_question_selection", fromlist=["refresh_document_control_answers"],
        ).refresh_document_control_answers(session, doc, model),
    )
    progress("Wzbogacanie dokumentu zakończone")
    return results
