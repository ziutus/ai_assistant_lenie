from unittest.mock import MagicMock, patch

from library.tracking_urls import is_tracking_url, resolve_tracking_url, resolve_tracking_urls_in_text


KIT_URL = (
    "https://30e6d271.click.kit-mail3.com/xmu6ek08x7h6hpq0e3eb5h20d3k8otnh2w3qm/"
    "dpheh0held858zamh4/aHR0cHM6Ly9ibG9nLmdvb2dsZS9zZWN1cml0eS9jaHJvbWUtc3Ryb25nZXItd2l0aC1ldmVyeS11cGRhdGUv"
)
DESTINATION = "https://blog.google/security/chrome-stronger-with-every-update/"
CANONICAL_DESTINATION = "https://blog.google/security/chrome-stronger-with-every-update"
GENERIC_TRACKING_URL = "https://click.example.com/redirect"


def _response(status_code=200, location=None):
    response = MagicMock()
    response.status_code = status_code
    response.is_redirect = location is not None
    response.is_permanent_redirect = False
    response.headers = {"Location": location} if location else {}
    return response


def test_recognizes_kit_tracking_host_with_hyphen():
    assert is_tracking_url(KIT_URL)


@patch("library.tracking_urls.validate_url_target")
@patch("library.tracking_urls.requests.request")
def test_decodes_kit_tracking_link_without_request(mock_request, mock_validate):
    assert resolve_tracking_url(KIT_URL) == CANONICAL_DESTINATION
    mock_request.assert_not_called()
    mock_validate.assert_not_called()


@patch("library.tracking_urls.requests.request")
def test_replaces_embedded_kit_link_in_plain_email_text_without_request(mock_request):
    text = f"Incident Impact: policzyłem ({KIT_URL})"

    assert resolve_tracking_urls_in_text(text) == f"Incident Impact: policzyłem ({CANONICAL_DESTINATION})"
    mock_request.assert_not_called()


@patch("library.tracking_urls.validate_url_target")
@patch("library.tracking_urls.requests.request")
def test_resolves_redirect_based_tracking_link(mock_request, mock_validate):
    mock_request.side_effect = [_response(302, DESTINATION), _response(200)]

    assert resolve_tracking_url(GENERIC_TRACKING_URL) == CANONICAL_DESTINATION
    assert mock_request.call_args_list[0].args[:2] == ("HEAD", GENERIC_TRACKING_URL)
    assert mock_validate.call_count == 2


@patch("library.tracking_urls.validate_url_target")
@patch("library.tracking_urls.requests.request")
def test_falls_back_to_streamed_get_when_head_is_rejected(mock_request, mock_validate):
    mock_request.side_effect = [_response(405), _response(302, DESTINATION), _response(200)]

    assert resolve_tracking_url(GENERIC_TRACKING_URL) == CANONICAL_DESTINATION
    assert [call.args[0] for call in mock_request.call_args_list] == ["HEAD", "GET", "GET"]
    assert mock_request.call_args_list[1].kwargs["stream"] is True


def test_does_not_fetch_regular_url():
    url = "https://example.com/article"
    with patch("library.tracking_urls.requests.request") as mock_request:
        assert resolve_tracking_url(url) == url
    mock_request.assert_not_called()
