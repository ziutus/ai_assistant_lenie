"""HTTP contract for search-rebuild stage 8."""

from __future__ import annotations

from dataclasses import fields
from datetime import date, datetime
import logging

from flask import Blueprint, jsonify, request

from library.db.engine import get_scoped_session
from library.publisher_registry import resolve_publisher
from library.search.audit_repository import parsed_query_to_dict, record_feedback
from library.search.name_resolution import resolve_author_name, resolve_discovery_source_name
from library.search.parser import build_parsed_query, parse_search_query
from library.search.types import (
    ParsedSearchQuery,
    SearchFeedback,
    SearchFilters,
    SearchQueryValidationError,
    SearchRequest,
)
from library.search_service import SearchService

logger = logging.getLogger(__name__)
bp = Blueprint("search", __name__)

_REQUEST_FIELDS = {"natural_query", "query", "filters", "limit", "offset", "sort"}
_FILTER_FIELDS = {field.name for field in fields(SearchFilters)}
_DATE_FIELDS = {"published_on_from", "published_on_to"}
_DATETIME_FIELDS = {"ingested_at_from", "ingested_at_to"}


def _json_object() -> dict:
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        raise SearchQueryValidationError("body", "expected a JSON object")
    return payload


def _filters_from_json(payload) -> SearchFilters:
    if payload is None:
        return SearchFilters()
    if not isinstance(payload, dict):
        raise SearchQueryValidationError("filters", "expected an object")
    unknown = set(payload) - _FILTER_FIELDS
    if unknown:
        raise SearchQueryValidationError("filters", f"unknown fields: {', '.join(sorted(unknown))}")
    values = dict(payload)
    try:
        for field_name in _DATE_FIELDS:
            if values.get(field_name) is not None:
                values[field_name] = date.fromisoformat(values[field_name])
        for field_name in _DATETIME_FIELDS:
            if values.get(field_name) is not None:
                values[field_name] = datetime.fromisoformat(values[field_name])
    except (TypeError, ValueError) as exc:
        raise SearchQueryValidationError("filters", "invalid ISO date/datetime") from exc
    return SearchFilters(**values)


def _request_from_json(payload: dict) -> SearchRequest:
    unknown = set(payload) - _REQUEST_FIELDS
    if unknown:
        raise SearchQueryValidationError("body", f"unknown fields: {', '.join(sorted(unknown))}")
    return SearchRequest(
        natural_query=payload.get("natural_query"),
        query=payload.get("query"),
        filters=_filters_from_json(payload.get("filters")),
        limit=payload.get("limit", 10),
        offset=payload.get("offset", 0),
        sort=payload.get("sort", "relevance"),
    )


def _parse_payload(result) -> dict:
    return {
        "search_id": result.interpretation_log_id,
        "interpretation": parsed_query_to_dict(result.parsed_query),
        "status": result.status.value,
        "fallback_used": result.fallback_used,
        "model": result.model,
        "error_code": result.error_code,
    }


def _ambiguities(session, parsed: ParsedSearchQuery) -> list[dict]:
    """Return all N>1 name resolutions; resolver failure degrades safely."""
    checks = []
    try:
        if parsed.author_name:
            checks.append(("author_name", resolve_author_name(session, parsed.author_name)))
        if parsed.publisher_name or parsed.publisher_domain:
            checks.append(("publisher", resolve_publisher(
                session, name=parsed.publisher_name, domain=parsed.publisher_domain,
            )))
        if parsed.discovery_source_name:
            checks.append(("discovery_source_name", resolve_discovery_source_name(
                session, parsed.discovery_source_name,
            )))
    except Exception:
        logger.exception("Name resolution failed; continuing with SQL filter fallback")
        return []
    return [
        {"field": field_name, "count": resolution.count}
        for field_name, resolution in checks if resolution.count > 1
    ]


@bp.post("/search/parse")
def parse_search():
    try:
        payload = _json_object()
        if set(payload) != {"natural_query"}:
            raise SearchQueryValidationError("body", "expected only natural_query")
        natural_query = payload.get("natural_query")
        if not isinstance(natural_query, str) or not natural_query.strip():
            raise SearchQueryValidationError("natural_query", "expected non-empty string")
    except SearchQueryValidationError as exc:
        return jsonify({"status": "error", "field": exc.field, "message": str(exc)}), 400
    return jsonify(_parse_payload(parse_search_query(natural_query))), 200


@bp.post("/search")
def execute_search():
    try:
        search_request = _request_from_json(_json_object())
    except SearchQueryValidationError as exc:
        return jsonify({"status": "error", "field": exc.field, "message": str(exc)}), 400

    if search_request.is_natural:
        parse_result = parse_search_query(search_request.natural_query)
        parsed = parse_result.parsed_query
        limit, offset = search_request.limit, search_request.offset
        sort = parsed.sort
        response = _parse_payload(parse_result)
    else:
        parsed = ParsedSearchQuery(
            query=search_request.query,
            **{field.name: getattr(search_request.filters, field.name) for field in fields(SearchFilters)},
            sort=search_request.sort,
            interpretation_summary="Jawne kryteria wyszukiwania (bez interpretacji LLM).",
        )
        limit, offset, sort = search_request.limit, search_request.offset, search_request.sort
        response = {
            "search_id": None,
            "interpretation": parsed_query_to_dict(parsed),
            "status": "explicit",
            "fallback_used": False,
            "model": None,
            "error_code": None,
        }

    ambiguities = _ambiguities(get_scoped_session(), parsed)
    if parsed.clarification_required or ambiguities:
        response.update({
            "results": [],
            "pagination": {
                "limit": limit, "offset": offset, "returned": 0, "has_more": False,
            },
            "clarification_required": True,
            "clarification_question": parsed.clarification_question,
            "ambiguities": ambiguities,
        })
        return jsonify(response), 200

    try:
        results_with_sentinel = SearchService(get_scoped_session()).search(
            parsed.query, parsed.to_filters(), limit=limit + 1, offset=offset, sort=sort,
        )
    except RuntimeError:
        logger.exception("Search execution failed")
        return jsonify({"status": "error", "message": "Search execution failed"}), 503

    has_more = len(results_with_sentinel) > limit
    results = results_with_sentinel[:limit]
    response.update({
        "results": results,
        "pagination": {
            "limit": limit, "offset": offset, "returned": len(results), "has_more": has_more,
        },
        "clarification_required": False,
        "clarification_question": None,
        "ambiguities": [],
    })
    return jsonify(response), 200


@bp.post("/search/<int:search_id>/feedback")
def search_feedback(search_id: int):
    try:
        payload = _json_object()
        unknown = set(payload) - {"verdict", "comment", "corrected_query"}
        if unknown:
            raise SearchQueryValidationError("body", f"unknown fields: {', '.join(sorted(unknown))}")
        corrected = payload.get("corrected_query")
        if corrected is not None and not isinstance(corrected, dict):
            raise SearchQueryValidationError("corrected_query", "expected an object")
        feedback = SearchFeedback(
            verdict=payload.get("verdict"),
            comment=payload.get("comment"),
            corrected_query=build_parsed_query(corrected) if corrected is not None else None,
        )
    except (SearchQueryValidationError, TypeError, ValueError) as exc:
        field = exc.field if isinstance(exc, SearchQueryValidationError) else "corrected_query"
        return jsonify({"status": "error", "field": field, "message": str(exc)}), 400
    if not record_feedback(search_id, feedback):
        return jsonify({"status": "error", "message": "Search interpretation not found"}), 404
    return jsonify({"status": "success", "search_id": search_id}), 200
