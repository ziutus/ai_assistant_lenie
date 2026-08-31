from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

pytest.importorskip("sqlalchemy")

from library.document_promotion import PromotionError, promote_link_to_webpage


class MemoryStorage:
    def __init__(self):
        self.objects = {}

    def put_bytes(self, key, data, content_type=None):
        self.objects[key] = data

    def get_bytes(self, key):
        return self.objects[key]

    def exists(self, key):
        return key in self.objects


def _make_doc(**overrides):
    doc = SimpleNamespace(
        id=42,
        uuid="uuid-42",
        url="https://example.test/article",
        document_type="link",
        paywall=False,
        requires_login=False,
        text=None,
        text_raw=None,
        text_md=None,
        text_extracted=None,
        byline="Original Byline",
        collection_id=7,
        processing_status="READY_FOR_EMBEDDING",
        processing_error_code=None,
    )
    doc.set_document_type = lambda value: setattr(doc, "document_type", value)
    doc.set_processing_status = lambda value: setattr(doc, "processing_status", value)
    for key, value in overrides.items():
        setattr(doc, key, value)
    return doc


def test_promotes_link_with_supplied_html():
    session, storage, doc = MagicMock(), MemoryStorage(), _make_doc()
    with patch("library.feed_monitor_service.link_matching_feed_items_to_document") as link_match:
        result = promote_link_to_webpage(session, storage, doc, html="<html><body>hi</body></html>")

    assert result is doc
    assert doc.document_type == "webpage"
    assert doc.text_raw == "<html><body>hi</body></html>"
    assert doc.processing_status == "NEED_CLEAN_MD"
    assert storage.objects["uuid-42.html"] == b"<html><body>hi</body></html>"
    link_match.assert_called_once()
    session.commit.assert_not_called()
    # metadata + identity untouched
    assert doc.byline == "Original Byline"
    assert doc.id == 42 and doc.collection_id == 7


def test_downloads_html_when_none_supplied():
    session, storage, doc = MagicMock(), MemoryStorage(), _make_doc()
    downloader = MagicMock(return_value=b"<html>downloaded</html>")
    with patch("library.feed_monitor_service.link_matching_feed_items_to_document"):
        promote_link_to_webpage(
            session, storage, doc, downloader=downloader, paid_check=lambda _u: False,
        )
    downloader.assert_called_once_with(doc.url)
    assert doc.text_raw == "<html>downloaded</html>"


def test_supplied_html_skips_downloader():
    downloader = MagicMock()
    with patch("library.feed_monitor_service.link_matching_feed_items_to_document"):
        promote_link_to_webpage(MagicMock(), MemoryStorage(), _make_doc(), html="<p>x</p>", downloader=downloader)
    downloader.assert_not_called()


@pytest.mark.parametrize("field,reason", [("paywall", "paywall"), ("requires_login", "requires_login")])
def test_wall_guard_raises_without_mutation(field, reason):
    doc = _make_doc(**{field: True})
    with pytest.raises(PromotionError) as exc:
        promote_link_to_webpage(MagicMock(), MemoryStorage(), doc)
    assert exc.value.reason == reason
    assert doc.document_type == "link"
    assert doc.text_raw is None


def test_non_link_non_webpage_raises_not_a_link():
    with pytest.raises(PromotionError) as exc:
        promote_link_to_webpage(MagicMock(), MemoryStorage(), _make_doc(document_type="youtube"))
    assert exc.value.reason == "not_a_link"


def test_download_failure_raises():
    with pytest.raises(PromotionError) as exc:
        promote_link_to_webpage(
            MagicMock(), MemoryStorage(), _make_doc(),
            downloader=lambda _u: None, paid_check=lambda _u: False,
        )
    assert exc.value.reason == "download_failed"


def test_paid_check_blocks_server_download():
    with pytest.raises(PromotionError) as exc:
        promote_link_to_webpage(
            MagicMock(), MemoryStorage(), _make_doc(),
            downloader=MagicMock(), paid_check=lambda _u: True,
        )
    assert exc.value.reason == "paywall"


def test_already_webpage_without_html_is_noop():
    doc = _make_doc(document_type="webpage", text_md="existing")
    result = promote_link_to_webpage(MagicMock(), MemoryStorage(), doc)
    assert result is doc
    assert doc.text_md == "existing"


def test_already_webpage_with_html_reattaches_source():
    session, storage = MagicMock(), MemoryStorage()
    doc = _make_doc(document_type="webpage", text_md="stale", text_extracted="stale",
                    processing_error_code="ERROR_DOWNLOAD")
    promote_link_to_webpage(session, storage, doc, html="<p>fresh</p>")
    assert doc.text_md is None and doc.text_extracted is None
    assert doc.text_raw == "<p>fresh</p>"
    assert doc.processing_error_code is None
    assert doc.processing_status == "NEED_CLEAN_MD"
    assert storage.objects["uuid-42.html"] == b"<p>fresh</p>"


def test_feed_linking_can_be_disabled():
    with patch("library.feed_monitor_service.link_matching_feed_items_to_document") as link_match:
        promote_link_to_webpage(MagicMock(), MemoryStorage(), _make_doc(), html="<p>x</p>",
                                run_feed_linking=False)
    link_match.assert_not_called()
