"""Unit tests for library/document_image_download.py (copy web images into storage)."""

from unittest.mock import MagicMock

import pytest

pytest.importorskip("sqlalchemy")
pytest.importorskip("requests")

from library import document_image_download as dl  # noqa: E402
from library.db.models import DocumentImage  # noqa: E402


def _row(image_id, url="https://example.com/a.jpg", storage_key=None):
    row = DocumentImage(document_id=7, position=0, url=url, storage_key=storage_key)
    row.id = image_id
    return row


def _session(rows):
    session = MagicMock(spec=["execute", "commit"])
    session.execute.return_value.scalars.return_value = iter(rows)
    return session


class TestStorageKey:
    def test_extension_from_content_type(self):
        assert dl.storage_key_for(7, 11, "image/jpeg") == "documents/7/web_images/11.jpg"
        assert dl.storage_key_for(7, 11, "image/webp") == "documents/7/web_images/11.webp"


class TestSsrfGuard:
    @pytest.mark.parametrize("url", [
        "ftp://example.com/a.jpg",
        "file:///etc/passwd",
        "http://127.0.0.1/a.jpg",
        "http://192.168.200.7:9000/bucket/a.jpg",
        "http://169.254.169.254/latest/meta-data",
    ])
    def test_rejects_non_public_targets(self, url):
        with pytest.raises(dl.ImageDownloadError):
            dl._assert_public_http_url(url)


class TestDownloadDocumentImages:
    def test_stores_image_and_sets_storage_key(self):
        row = _row(11)
        storage = MagicMock()
        session = _session([row])
        fetcher = MagicMock(return_value=(b"\xff\xd8data", "image/jpeg"))

        results = dl.download_document_images(session, storage, 7, [11], fetcher=fetcher)

        assert results == [{"id": 11, "status": "stored"}]
        storage.put_bytes.assert_called_once_with("documents/7/web_images/11.jpg", b"\xff\xd8data", "image/jpeg")
        assert row.storage_key == "documents/7/web_images/11.jpg"
        session.commit.assert_called_once()

    def test_already_stored_image_is_not_fetched_again(self):
        row = _row(11, storage_key="documents/7/web_images/11.jpg")
        fetcher = MagicMock()

        results = dl.download_document_images(_session([row]), MagicMock(), 7, fetcher=fetcher)

        assert results == [{"id": 11, "status": "already_stored"}]
        fetcher.assert_not_called()

    def test_one_failure_does_not_abort_the_rest(self):
        good, bad = _row(1, "https://example.com/1.jpg"), _row(2, "https://example.com/2.jpg")
        storage = MagicMock()

        def fetcher(url):
            if url.endswith("2.jpg"):
                raise dl.ImageDownloadError("Serwer odpowiedział kodem 404.")
            return b"x", "image/png"

        results = dl.download_document_images(_session([good, bad]), storage, 7, fetcher=fetcher)

        by_id = {r["id"]: r for r in results}
        assert by_id[1]["status"] == "stored"
        assert by_id[2] == {"id": 2, "status": "error", "message": "Serwer odpowiedział kodem 404."}
        assert good.storage_key and bad.storage_key is None

    def test_storage_write_failure_is_reported_not_raised(self):
        row = _row(1)
        storage = MagicMock()
        storage.put_bytes.side_effect = RuntimeError("minio down")

        results = dl.download_document_images(
            _session([row]), storage, 7, fetcher=lambda url: (b"x", "image/png"),
        )

        assert results[0]["status"] == "error"
        assert row.storage_key is None
