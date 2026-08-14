from datetime import datetime
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from flask import Flask

from library.service_status_routes import bp


def _response(*, successes: int, failures: int, error: str | None = None,
              webshare_successes: int = 0, webshare_failures: int = 0):
    session = MagicMock()
    cloudferro = [
        MagicMock(one=lambda: SimpleNamespace(
            successes=successes, failures=failures,
            last_success_at=datetime(2026, 8, 13, 10, 0) if successes else None,
            last_failure_at=datetime(2026, 8, 13, 10, 1) if failures else None,
        )),
        MagicMock(one_or_none=lambda: SimpleNamespace(operation="llm_call", error_code=error) if error else None),
    ]
    empty = [
        MagicMock(one=lambda: SimpleNamespace(successes=0, failures=0, last_success_at=None, last_failure_at=None)),
        MagicMock(one_or_none=lambda: None),
    ]
    webshare = [
        MagicMock(one=lambda: SimpleNamespace(
            successes=webshare_successes, failures=webshare_failures,
            last_success_at=datetime(2026, 8, 13, 10, 2) if webshare_successes else None,
            last_failure_at=datetime(2026, 8, 13, 10, 3) if webshare_failures else None,
        )),
        MagicMock(one_or_none=lambda: SimpleNamespace(operation="subscription_plan", error_code="HTTP_503") if webshare_failures else None),
    ]
    # CloudFerro, ARK Labs, OpenAI, Bedrock, Vertex, Webshare, LocationIQ,
    # Wikidata, Overpass — two queries per card.
    session.execute.side_effect = cloudferro + empty * 4 + webshare + empty * 3
    app = Flask(__name__)
    app.register_blueprint(bp)
    with patch("library.service_status_routes.get_scoped_session", return_value=session):
        response = app.test_client().get("/service_status")
    return response.get_json()


def test_cloudferro_is_down_when_all_recent_calls_failed():
    data = _response(successes=0, failures=3, error="APITimeoutError")
    service = data["services"][0]
    assert service["status"] == "down"
    assert service["last_error_code"] == "APITimeoutError"
    assert service["last_failure_at"].endswith("Z")
    assert data["observed_at"].endswith("Z")


def test_cloudferro_is_warning_when_successes_and_failures_mix():
    data = _response(successes=2, failures=1, error="APIConnectionError")
    assert data["services"][0]["status"] == "warning"


def test_cloudferro_is_unknown_without_recent_calls():
    data = _response(successes=0, failures=0)
    assert data["services"][0]["status"] == "unknown"


def test_webshare_status_includes_last_real_operation():
    data = _response(successes=0, failures=0, webshare_successes=1, webshare_failures=1)
    webshare = next(service for service in data["services"] if service["id"] == "webshare")
    assert webshare["status"] == "warning"
    assert webshare["last_operation"] == "subscription_plan"
    assert webshare["last_error_code"] == "HTTP_503"
