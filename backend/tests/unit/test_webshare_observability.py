from types import SimpleNamespace
from unittest.mock import patch

from library.webshare_ip_auth import _request


def test_webshare_request_records_success():
    response = SimpleNamespace(ok=True, status_code=200)
    with patch("library.webshare_ip_auth.requests.request", return_value=response), patch(
        "library.external_service_events.record_external_service_event"
    ) as record:
        assert _request("profile", "GET", "https://example.test", timeout=1) is response

    assert record.call_args.kwargs["service"] == "webshare"
    assert record.call_args.kwargs["operation"] == "profile"
    assert record.call_args.kwargs["success"] is True


def test_webshare_http_failure_records_status_code():
    response = SimpleNamespace(ok=False, status_code=429)
    with patch("library.webshare_ip_auth.requests.request", return_value=response), patch(
        "library.external_service_events.record_external_service_event"
    ) as record:
        _request("subscription_plan", "GET", "https://example.test", timeout=1)

    assert record.call_args.kwargs["success"] is False
    assert record.call_args.kwargs["error_code"] == "HTTP_429"
