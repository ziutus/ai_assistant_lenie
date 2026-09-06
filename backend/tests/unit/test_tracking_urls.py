from unittest.mock import MagicMock, patch

import requests

from library.tracking_urls import is_tracking_url, resolve_tracking_url, resolve_tracking_urls_in_text


KIT_URL = (
    "https://30e6d271.click.kit-mail3.com/xmu6ek08x7h6hpq0e3eb5h20d3k8otnh2w3qm/"
    "dpheh0held858zamh4/aHR0cHM6Ly9ibG9nLmdvb2dsZS9zZWN1cml0eS9jaHJvbWUtc3Ryb25nZXItd2l0aC1ldmVyeS11cGRhdGUv"
)
DESTINATION = "https://blog.google/security/chrome-stronger-with-every-update/"
CANONICAL_DESTINATION = "https://blog.google/security/chrome-stronger-with-every-update"
GENERIC_TRACKING_URL = "https://click.example.com/redirect"


def _response(status_code=200, url=DESTINATION):
    response = MagicMock(spec=requests.Response)
    response.status_code = status_code
    response.url = url
    return response


def test_recognizes_kit_tracking_host_with_hyphen():
    assert is_tracking_url(KIT_URL)


@patch("library.tracking_urls.safe_get")
def test_decodes_kit_tracking_link_without_request(mock_safe_get):
    assert resolve_tracking_url(KIT_URL) == CANONICAL_DESTINATION
    mock_safe_get.assert_not_called()


@patch("library.tracking_urls.safe_get")
def test_replaces_embedded_kit_link_in_plain_email_text_without_request(mock_safe_get):
    text = f"Incident Impact: policzyłem ({KIT_URL})"

    assert resolve_tracking_urls_in_text(text) == f"Incident Impact: policzyłem ({CANONICAL_DESTINATION})"
    mock_safe_get.assert_not_called()


@patch("library.tracking_urls.safe_get")
def test_resolves_redirect_based_tracking_link(mock_safe_get):
    # safe_get follows the redirect chain internally and reports the final URL.
    mock_safe_get.return_value = _response(200, url=DESTINATION)

    assert resolve_tracking_url(GENERIC_TRACKING_URL) == CANONICAL_DESTINATION
    assert mock_safe_get.call_args.args[0] == GENERIC_TRACKING_URL
    assert mock_safe_get.call_args.kwargs["method"] == "HEAD"


@patch("library.tracking_urls.safe_get")
def test_falls_back_to_get_when_head_is_rejected(mock_safe_get):
    mock_safe_get.side_effect = [_response(405, url=GENERIC_TRACKING_URL), _response(200, url=DESTINATION)]

    assert resolve_tracking_url(GENERIC_TRACKING_URL) == CANONICAL_DESTINATION
    assert [call.kwargs["method"] for call in mock_safe_get.call_args_list] == ["HEAD", "GET"]


@patch("library.tracking_urls.safe_get")
def test_returns_original_url_when_every_attempt_fails(mock_safe_get):
    mock_safe_get.side_effect = requests.ConnectionError("boom")

    assert resolve_tracking_url(GENERIC_TRACKING_URL) == GENERIC_TRACKING_URL
    assert [call.kwargs["method"] for call in mock_safe_get.call_args_list] == ["HEAD", "GET"]


@patch("library.tracking_urls.safe_get")
def test_redirect_to_internal_service_yields_original_url(mock_safe_get):
    mock_safe_get.side_effect = ValueError("URL resolves to a non-public address")

    assert resolve_tracking_url(GENERIC_TRACKING_URL) == GENERIC_TRACKING_URL


@patch("library.tracking_urls.safe_get")
def test_does_not_fetch_regular_url(mock_safe_get):
    url = "https://example.com/article"
    assert resolve_tracking_url(url) == url
    mock_safe_get.assert_not_called()
