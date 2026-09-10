"""Piggyback transport shared by the two existing execution endpoints."""

from functools import wraps
from time import perf_counter

from flask import g, make_response, request

from library.browse_events import record_browse_event, telemetry_context


def browse_execution(source_view, *, correction=False):
    def decorate(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            started = perf_counter()
            payload = request.get_json(silent=True) if source_view == "search" else None
            raw = (
                (payload.get("telemetry") if isinstance(payload, dict) else None)
                if source_view == "search"
                else {
                    key.removeprefix("_tel_"): value for key, value in request.args.items() if key.startswith("_tel_")
                }
            )
            context = telemetry_context(raw)
            g.browse_event = dict(
                filters={},
                query_text=None,
                effective_query=None,
                sort="newest" if source_view == "document_list" else "relevance",
                page_size=100 if source_view == "document_list" else 10,
                offset=0,
                execution_mode="ilike" if source_view == "document_list" else "validation",
            )
            if isinstance(payload, dict):
                query = payload.get("natural_query", payload.get("query"))
                if isinstance(query, str):
                    g.browse_event["query_text"] = query
            elif source_view == "document_list":
                g.browse_event["query_text"] = request.args.get("search_in_document")
            response = None
            try:
                response = make_response(view(*args, **kwargs))
                return response
            finally:
                if context:
                    body = response.get_json(silent=True) if response is not None else {}
                    body = body or {}
                    values = g.browse_event
                    outcome = (
                        "error"
                        if response is None or response.status_code >= 400
                        else ("clarification_required" if body.get("clarification_required") else "success")
                    )
                    if correction:
                        context["action"] = "correction"
                        values["execution_mode"] = "feedback"
                    applied_fields = set(values["filters"]) | {"query", "sort", "page_size", "requested_mode"}
                    context["changed_fields"] = [
                        field for field in context["changed_fields"] if field in applied_fields
                    ]
                    context["criteria_origin"] = {
                        field: context["criteria_origin"].get(field, "default") for field in applied_fields
                    }
                    if values["execution_mode"] == "natural":
                        for field in set(values["filters"]) | {"sort"}:
                            context["criteria_origin"][field] = "ai"
                        context["changed_fields"] = [
                            field
                            for field in context["changed_fields"]
                            if field not in values["filters"] and field != "sort"
                        ]
                    pagination = body.get("pagination", {})
                    returned = len(body["websites"]) if "websites" in body else pagination.get("returned")
                    total = body.get("all_results_count")
                    has_more = pagination.get("has_more")
                    if total is not None and returned is not None:
                        has_more = values["offset"] + returned < total
                    record_browse_event(
                        **context,
                        **values,
                        source_view=source_view,
                        outcome=outcome,
                        returned_count=returned,
                        total_count=total,
                        has_more=has_more,
                        duration_ms=round((perf_counter() - started) * 1000),
                    )

        return wrapped

    return decorate
