from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import flask
import pytest

from library.search.parser import SearchQueryParseResult
from library.search.types import (
    InterpretationStatus,
    ParsedSearchQuery,
    SearchSort,
)
import library.search_routes as routes


@pytest.fixture()
def client():
    app = flask.Flask(__name__)
    app.register_blueprint(routes.bp)
    app.config["TESTING"] = True
    return app.test_client()


def _parse_result(**parsed_overrides):
    parsed = ParsedSearchQuery(
        query="wojna",
        interpretation_summary="Wojna po 1945",
        **parsed_overrides,
    )
    return SearchQueryParseResult(
        parsed_query=parsed,
        status=InterpretationStatus.PARSED,
        fallback_used=False,
        interpretation_log_id=123,
        model="bielik",
        raw_response="{}",
        error_code=None,
        error_message=None,
        llm_latency_ms=10,
        usage=None,
    )


class TestParseEndpoint:
    def test_returns_interpretation_without_searching(self, client):
        with patch.object(routes, "parse_search_query", return_value=_parse_result()) as parse:
            with patch.object(routes, "SearchService") as service:
                response = client.post("/search/parse", json={"natural_query": "wojna po 1945"})
        assert response.status_code == 200
        body = response.get_json()
        assert body["search_id"] == 123
        assert body["interpretation"]["query"] == "wojna"
        assert body["status"] == "parsed"
        parse.assert_called_once_with("wojna po 1945")
        service.assert_not_called()

    @pytest.mark.parametrize("payload", [None, {}, {"natural_query": ""}, {"query": "x"},
                                          {"natural_query": "x", "extra": 1}])
    def test_invalid_request_is_400(self, client, payload):
        response = client.post("/search/parse", json=payload)
        assert response.status_code == 400
        assert response.get_json()["status"] == "error"


class TestSearchEndpoint:
    def test_explicit_filter_only_skips_parser_and_calls_service(self, client):
        service = MagicMock()
        service.search.return_value = [{"document_id": 7}]
        with patch.object(routes, "SearchService", return_value=service):
            with patch.object(routes, "parse_search_query") as parser:
                with patch.object(routes, "get_scoped_session", return_value=MagicMock()):
                    response = client.post("/search", json={
                        "filters": {"languages": ["pl"], "published_on_from": "2020-01-01"},
                        "limit": 5,
                        "sort": "published_desc",
                    })
        assert response.status_code == 200
        body = response.get_json()
        assert body["status"] == "explicit"
        assert body["results"] == [{"document_id": 7}]
        assert body["pagination"] == {
            "limit": 5, "offset": 0, "returned": 1, "has_more": False,
        }
        parser.assert_not_called()
        args, kwargs = service.search.call_args
        assert args[0] is None
        assert args[1].languages == ("pl",)
        assert kwargs["sort"] is SearchSort.PUBLISHED_DESC
        assert kwargs["limit"] == 6

    def test_pagination_uses_extra_result_as_has_more_sentinel(self, client):
        service = MagicMock()
        service.search.return_value = [{"document_id": i} for i in range(1, 5)]
        with patch.object(routes, "SearchService", return_value=service):
            with patch.object(routes, "get_scoped_session", return_value=MagicMock()):
                response = client.post("/search", json={
                    "filters": {"languages": ["pl"]}, "limit": 3, "offset": 6,
                })
        body = response.get_json()
        assert [row["document_id"] for row in body["results"]] == [1, 2, 3]
        assert body["pagination"] == {
            "limit": 3, "offset": 6, "returned": 3, "has_more": True,
        }
        assert service.search.call_args.kwargs["limit"] == 4
        assert service.search.call_args.kwargs["offset"] == 6

    def test_natural_query_parses_and_executes(self, client):
        service = MagicMock()
        service.search.return_value = []
        with patch.object(routes, "parse_search_query", return_value=_parse_result()) as parser:
            with patch.object(routes, "SearchService", return_value=service):
                with patch.object(routes, "get_scoped_session", return_value=MagicMock()):
                    response = client.post("/search", json={"natural_query": "wojna", "limit": 4})
        assert response.status_code == 200
        assert response.get_json()["search_id"] == 123
        parser.assert_called_once_with("wojna")
        service.search.assert_called_once()

    def test_parser_fallback_still_searches_literal_query(self, client):
        result = _parse_result()
        result = SearchQueryParseResult(
            **{**result.__dict__, "status": InterpretationStatus.LLM_ERROR, "fallback_used": True},
        )
        service = MagicMock()
        service.search.return_value = []
        with patch.object(routes, "parse_search_query", return_value=result):
            with patch.object(routes, "SearchService", return_value=service):
                with patch.object(routes, "get_scoped_session", return_value=MagicMock()):
                    response = client.post("/search", json={"natural_query": "wojna"})
        assert response.status_code == 200
        assert response.get_json()["fallback_used"] is True
        service.search.assert_called_once()

    def test_ambiguity_requests_clarification_without_search(self, client):
        resolution = SimpleNamespace(count=2)
        with patch.object(routes, "resolve_author_name", return_value=resolution):
            with patch.object(routes, "get_scoped_session", return_value=MagicMock()):
                with patch.object(routes, "SearchService") as service:
                    response = client.post("/search", json={
                        "filters": {"author_name": "Artur Rubinstein"},
                    })
        body = response.get_json()
        assert response.status_code == 200
        assert body["clarification_required"] is True
        assert body["ambiguities"] == [{"count": 2, "field": "author_name"}]
        assert body["results"] == []
        service.assert_not_called()

    def test_resolver_failure_does_not_return_500(self, client):
        service = MagicMock()
        service.search.return_value = []
        with patch.object(routes, "resolve_author_name", side_effect=RuntimeError("db")):
            with patch.object(routes, "SearchService", return_value=service):
                with patch.object(routes, "get_scoped_session", return_value=MagicMock()):
                    response = client.post("/search", json={"filters": {"author_name": "Jan"}})
        assert response.status_code == 200
        service.search.assert_called_once()

    @pytest.mark.parametrize("payload", [None, {}, {"natural_query": "x", "query": "y"},
                                          {"filters": {"bad": 1}}, {"limit": 0},
                                          {"filters": {"published_on_from": "bad"}}])
    def test_invalid_contract_is_400(self, client, payload):
        response = client.post("/search", json=payload)
        assert response.status_code == 400

    def test_search_runtime_failure_is_safe_503(self, client):
        service = MagicMock()
        service.search.side_effect = RuntimeError("embedding secret detail")
        with patch.object(routes, "SearchService", return_value=service):
            with patch.object(routes, "get_scoped_session", return_value=MagicMock()):
                response = client.post("/search", json={"query": "x"})
        assert response.status_code == 503
        assert "secret detail" not in response.get_data(as_text=True)


class TestFeedbackEndpoint:
    def test_records_feedback(self, client):
        with patch.object(routes, "record_feedback", return_value=True) as record:
            response = client.post("/search/12/feedback", json={
                "verdict": "correct", "comment": "ok",
            })
        assert response.status_code == 200
        assert response.get_json() == {"search_id": 12, "status": "success"}
        assert record.call_args.args[0] == 12

    def test_unknown_search_is_404(self, client):
        with patch.object(routes, "record_feedback", return_value=False):
            response = client.post("/search/999/feedback", json={"verdict": "incorrect"})
        assert response.status_code == 404

    @pytest.mark.parametrize("payload", [{}, {"verdict": "wrong"}, {"verdict": "correct", "x": 1},
                                          {"verdict": "correct", "corrected_query": {}},
                                          {"verdict": "correct", "corrected_query": []}])
    def test_invalid_feedback_is_400(self, client, payload):
        response = client.post("/search/1/feedback", json=payload)
        assert response.status_code == 400
