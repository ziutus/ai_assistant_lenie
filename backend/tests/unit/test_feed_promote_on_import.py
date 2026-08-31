"""Feed-review "Zaimportuj jako webpage" promotes an existing link in place."""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

pytest.importorskip("sqlalchemy")

from library.feed_monitor_service import import_feed_item


def _item():
    return SimpleNamespace(
        id=17, feed_source_id=9, canonical_url="https://example.test/post",
        status="new", document_id=None, saved_at=None, saved_by_user_id=None,
        review_reason=None, ignored_pattern=None, group_memberships=[], last_error=None,
        updated_at=None, title="Post", summary=None, published_at=None,
        reviewed_by_user_id=None, reviewed_at=None,
    )


def _link_doc(**overrides):
    doc = SimpleNamespace(id=555, document_type="link", paywall=False, requires_login=False,
                          canonical_url="https://example.test/post")
    for key, value in overrides.items():
        setattr(doc, key, value)
    return doc


def _run(item, doc, *, document_type="webpage"):
    session = MagicMock()
    session.get.side_effect = lambda model, identifier: (
        item if identifier == 17 else doc if identifier == getattr(doc, "id", None) else SimpleNamespace(id=9)
    )
    with (
        patch("library.feed_monitor_service.Document.get_by_url", return_value=doc),
        patch("library.feed_monitor_service.DocumentService"),
        patch("library.feed_monitor_service.copy_feed_groups_to_document"),
        patch("library.feed_monitor_service.record_review_decision") as record,
        patch("library.document_promotion.promote_link_to_webpage") as promote,
        patch("library.document_processing_service.ensure_document_prepare_job") as ensure_job,
    ):
        import_feed_item(17, session=session, document_type=document_type, user_id=1)
    return promote, ensure_job, record, session


def test_existing_link_is_promoted_and_prepare_job_queued():
    promote, ensure_job, record, session = _run(_item(), _link_doc())

    promote.assert_called_once()
    assert promote.call_args.kwargs["run_feed_linking"] is False
    ensure_job.assert_called_once()
    # job is queued only after the single commit
    assert session.commit.called
    assert record.call_args.kwargs["metadata"]["promoted"] is True


def test_paywalled_link_stays_a_link():
    promote, ensure_job, record, _ = _run(_item(), _link_doc(paywall=True))

    promote.assert_not_called()
    ensure_job.assert_not_called()
    assert record.call_args.kwargs["metadata"]["promoted"] is False


def test_link_import_does_not_promote():
    promote, ensure_job, _, _ = _run(_item(), _link_doc(), document_type="link")

    promote.assert_not_called()
    ensure_job.assert_not_called()
