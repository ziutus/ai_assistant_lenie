"""Unit tests for src.api_client module."""

from unittest.mock import MagicMock, patch

import pytest
import requests

from src.api_client import (
    ApiConnectionError,
    ApiError,
    ApiResponseError,
    LenieApiClient,
    create_client,
)
from src.config import Config


BASE_URL = "http://localhost:5000"
API_KEY = "test-api-key-12345"


def _make_client() -> LenieApiClient:
    return LenieApiClient(BASE_URL, API_KEY)


def _mock_response(status_code: int = 200, json_data: dict | None = None, text: str = "") -> MagicMock:
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_data or {}
    resp.text = text
    return resp


# --- Task 1: Exception hierarchy tests ---


class TestExceptionHierarchy:
    """Tests for ApiError, ApiConnectionError, ApiResponseError."""

    def test_api_error_has_message(self):
        err = ApiError("something broke")
        assert err.message == "something broke"
        assert str(err) == "something broke"

    def test_api_connection_error_is_api_error(self):
        err = ApiConnectionError("timeout")
        assert isinstance(err, ApiError)
        assert err.message == "timeout"

    def test_api_response_error_is_api_error(self):
        err = ApiResponseError("bad request", status_code=400, response_body="invalid")
        assert isinstance(err, ApiError)
        assert err.message == "bad request"
        assert err.status_code == 400
        assert err.response_body == "invalid"

    def test_api_response_error_default_body(self):
        err = ApiResponseError("error", status_code=500)
        assert err.response_body == ""


# --- Task 4.1: Test get_version() ---


class TestGetVersion:
    def test_get_version_success(self):
        client = _make_client()
        mock_resp = _mock_response(200, {"status": "success", "app_version": "0.3.13.0", "app_build_time": "2026-01-01"})
        with patch.object(client._session, "request", return_value=mock_resp) as mock_req:
            result = client.get_version()
        assert result["app_version"] == "0.3.13.0"
        mock_req.assert_called_once_with("GET", f"{BASE_URL}/version", timeout=5)


# --- Task 4.2: Test add_url() ---


class TestAddUrl:
    def test_add_url_success(self):
        client = _make_client()
        mock_resp = _mock_response(200, {"status": "success", "message": "URL added", "id": 42})
        with patch.object(client._session, "request", return_value=mock_resp) as mock_req:
            result = client.add_url("https://example.com", "link")
        assert result["id"] == 42
        mock_req.assert_called_once_with(
            "POST", f"{BASE_URL}/url_add", timeout=5,
            json={"url": "https://example.com", "type": "link"},
        )

    def test_add_url_with_kwargs(self):
        client = _make_client()
        mock_resp = _mock_response(200, {"status": "success", "id": 99})
        with patch.object(client._session, "request", return_value=mock_resp) as mock_req:
            result = client.add_url("https://example.com", "webpage", title="Test", note="A note")
        assert result["id"] == 99
        call_json = mock_req.call_args[1]["json"]
        assert call_json["title"] == "Test"
        assert call_json["note"] == "A note"

    def test_add_url_default_type(self):
        client = _make_client()
        mock_resp = _mock_response(200, {"status": "success", "id": 1})
        with patch.object(client._session, "request", return_value=mock_resp) as mock_req:
            client.add_url("https://example.com")
        call_json = mock_req.call_args[1]["json"]
        assert call_json["type"] == "webpage"


# --- Task 4.3: Test get_document() ---


class TestGetDocument:
    def test_get_document_success(self):
        client = _make_client()
        doc = {"id": 123, "title": "Test Doc", "url": "https://example.com"}
        mock_resp = _mock_response(200, doc)
        with patch.object(client._session, "request", return_value=mock_resp) as mock_req:
            result = client.get_document(123)
        assert result["id"] == 123
        mock_req.assert_called_once_with("GET", f"{BASE_URL}/website_get", timeout=5, params={"id": 123})


# --- Task 4.4: Test get_count() ---


class TestGetCount:
    def test_get_count_success(self):
        client = _make_client()
        mock_resp = _mock_response(200, {"status": "success", "websites": [], "all_results_count": 42})
        with patch.object(client._session, "request", return_value=mock_resp) as mock_req:
            result = client.get_count("ALL")
        assert result == 42
        mock_req.assert_called_once_with("GET", f"{BASE_URL}/website_list", timeout=5, params={"type": "ALL"})

    def test_get_count_default_type(self):
        client = _make_client()
        mock_resp = _mock_response(200, {"status": "success", "websites": [], "all_results_count": 10})
        with patch.object(client._session, "request", return_value=mock_resp):
            result = client.get_count()
        assert result == 10


# --- Task 4.5: Test check_url() ---


class TestCheckUrl:
    def test_check_url_found(self):
        client = _make_client()
        doc = {"id": 5, "url": "https://example.com"}
        mock_resp = _mock_response(200, {"status": "success", "websites": [doc], "all_results_count": 1})
        with patch.object(client._session, "request", return_value=mock_resp) as mock_req:
            result = client.check_url("https://example.com")
        assert result == doc
        mock_req.assert_called_once_with(
            "GET", f"{BASE_URL}/website_list", timeout=5,
            params={"search_in_document": "https://example.com"},
        )

    def test_check_url_not_found(self):
        client = _make_client()
        mock_resp = _mock_response(200, {"status": "success", "websites": [], "all_results_count": 0})
        with patch.object(client._session, "request", return_value=mock_resp):
            result = client.check_url("https://nonexistent.com")
        assert result is None


# --- Task 4.6: Test connection timeout raises ApiConnectionError ---


class TestConnectionErrors:
    def test_connection_timeout_raises_api_connection_error(self):
        client = _make_client()
        with patch.object(client._session, "request", side_effect=requests.Timeout("timed out")):
            with pytest.raises(ApiConnectionError, match="(?i)timed out|timeout"):
                client.get_version()

    def test_connection_refused_raises_api_connection_error(self):
        client = _make_client()
        with patch.object(client._session, "request", side_effect=requests.ConnectionError("refused")):
            with pytest.raises(ApiConnectionError, match="(?i)connect"):
                client.get_version()

    def test_other_request_exception_raises_api_connection_error(self):
        client = _make_client()
        with patch.object(client._session, "request", side_effect=requests.TooManyRedirects("too many")):
            with pytest.raises(ApiConnectionError, match="Request failed"):
                client.get_version()


# --- Task 4.7: Test HTTP 500 raises ApiResponseError ---


class TestHttpErrors:
    def test_http_500_raises_api_response_error(self):
        client = _make_client()
        mock_resp = _mock_response(500, text="Internal Server Error")
        with patch.object(client._session, "request", return_value=mock_resp):
            with pytest.raises(ApiResponseError) as exc_info:
                client.get_version()
            assert exc_info.value.status_code == 500
            assert "Internal Server Error" in exc_info.value.response_body

    # --- Task 4.8: Test HTTP 401 raises ApiResponseError ---

    def test_http_401_raises_api_response_error(self):
        client = _make_client()
        mock_resp = _mock_response(401, text="Unauthorized")
        with patch.object(client._session, "request", return_value=mock_resp):
            with pytest.raises(ApiResponseError) as exc_info:
                client.add_url("https://example.com")
            assert exc_info.value.status_code == 401


# --- Task 4.9: Test x-api-key header is present ---


class TestHeaders:
    def test_api_key_header_set_on_session(self):
        client = _make_client()
        assert client._session.headers.get("x-api-key") == API_KEY
        assert client._session.headers.get("Content-Type") == "application/json"


# --- Task 4.10: Test create_client() ---


class TestCreateClient:
    def test_create_client_reads_config(self):
        cfg = Config({"LENIE_API_URL": "http://my-backend:5000", "STALKER_API_KEY": "secret-key"})
        client = create_client(cfg)
        assert isinstance(client, LenieApiClient)
        assert client._base_url == "http://my-backend:5000"
        assert client._api_key == "secret-key"

    def test_create_client_default_url(self):
        cfg = Config({"STALKER_API_KEY": "secret-key"})
        client = create_client(cfg)
        assert client._base_url == "http://lenie-ai-server:5000"

    def test_create_client_strips_trailing_slash(self):
        cfg = Config({"LENIE_API_URL": "http://my-backend:5000/", "STALKER_API_KEY": "key"})
        client = create_client(cfg)
        assert client._base_url == "http://my-backend:5000"


# --- Review fixes: malformed response and missing key tests ---


class TestMalformedResponse:
    def test_non_json_response_raises_api_response_error(self):
        client = _make_client()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.side_effect = requests.exceptions.JSONDecodeError("fail", "doc", 0)
        mock_resp.text = "<html>Gateway Timeout</html>"
        with patch.object(client._session, "request", return_value=mock_resp):
            with pytest.raises(ApiResponseError) as exc_info:
                client.get_version()
            assert exc_info.value.status_code == 200
            assert "non-JSON" in exc_info.value.message


class TestGetCountMissingKey:
    def test_get_count_missing_all_results_count_raises(self):
        client = _make_client()
        mock_resp = _mock_response(200, {"status": "success", "websites": []})
        with patch.object(client._session, "request", return_value=mock_resp):
            with pytest.raises(ApiResponseError, match="all_results_count"):
                client.get_count()
