"""Unit tests for SSRF protection in library/website/website_download_context.py."""
from unittest.mock import MagicMock, patch

import pytest

from library.website.website_download_context import download_raw_html, validate_url_target


class TestValidateUrlTarget:
    def test_rejects_non_http_scheme(self):
        with pytest.raises(ValueError, match="Unsupported URL scheme"):
            validate_url_target("ftp://example.com/file.txt")

    def test_rejects_file_scheme(self):
        with pytest.raises(ValueError, match="Unsupported URL scheme"):
            validate_url_target("file:///etc/passwd")

    def test_rejects_missing_hostname(self):
        with pytest.raises(ValueError, match="no hostname"):
            validate_url_target("http://")

    def test_rejects_loopback_address(self):
        with pytest.raises(ValueError, match="non-public address"):
            validate_url_target("http://127.0.0.1:5000/admin")

    def test_rejects_private_address(self):
        with pytest.raises(ValueError, match="non-public address"):
            validate_url_target("http://192.168.200.7:5434/")

    def test_rejects_link_local_address(self):
        # AWS/GCP metadata endpoint — classic SSRF target
        with pytest.raises(ValueError, match="non-public address"):
            validate_url_target("http://169.254.169.254/latest/meta-data/")

    def test_rejects_unresolvable_hostname(self):
        with pytest.raises(ValueError, match="Cannot resolve"):
            validate_url_target("http://nonexistent-domain-lenie-test.invalid/")

    def test_accepts_public_address(self):
        validate_url_target("https://1.1.1.1/")


class TestDownloadRawHtml:
    @patch("library.website.website_download_context.requests.get")
    def test_downloads_content_with_timeout(self, mock_get):
        response = MagicMock()
        response.status_code = 200
        response.content = b"<html></html>"
        response.is_redirect = False
        response.is_permanent_redirect = False
        mock_get.return_value = response

        result = download_raw_html("https://1.1.1.1/page")

        assert result == b"<html></html>"
        assert mock_get.call_args.kwargs["timeout"] == 30
        assert mock_get.call_args.kwargs["allow_redirects"] is False

    @patch("library.website.website_download_context.requests.get")
    def test_returns_none_on_error_status(self, mock_get):
        response = MagicMock()
        response.status_code = 404
        response.is_redirect = False
        response.is_permanent_redirect = False
        mock_get.return_value = response

        assert download_raw_html("https://1.1.1.1/missing") is None

    @patch("library.website.website_download_context.requests.get")
    def test_rejects_redirect_to_private_address(self, mock_get):
        response = MagicMock()
        response.is_redirect = True
        response.is_permanent_redirect = False
        response.headers = {"Location": "http://192.168.1.1/internal"}
        mock_get.return_value = response

        with pytest.raises(ValueError, match="non-public address"):
            download_raw_html("https://1.1.1.1/redirect")

    @patch("library.website.website_download_context.requests.get")
    def test_follows_public_redirect(self, mock_get):
        redirect = MagicMock()
        redirect.is_redirect = True
        redirect.is_permanent_redirect = False
        redirect.headers = {"Location": "https://1.0.0.1/final"}

        final = MagicMock()
        final.status_code = 200
        final.content = b"ok"
        final.is_redirect = False
        final.is_permanent_redirect = False

        mock_get.side_effect = [redirect, final]

        assert download_raw_html("https://1.1.1.1/start") == b"ok"

    @patch("library.website.website_download_context.requests.get")
    def test_raises_on_redirect_loop(self, mock_get):
        response = MagicMock()
        response.is_redirect = True
        response.is_permanent_redirect = False
        response.headers = {"Location": "https://1.1.1.1/loop"}
        mock_get.return_value = response

        with pytest.raises(ValueError, match="Too many redirects"):
            download_raw_html("https://1.1.1.1/loop")

    def test_rejects_private_url_before_any_request(self):
        with pytest.raises(ValueError, match="non-public address"):
            download_raw_html("http://127.0.0.1:8080/")
