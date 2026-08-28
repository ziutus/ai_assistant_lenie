from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest
from flask import Flask, g
from werkzeug.exceptions import BadRequest

from library.legacy_aws_pull_service import LegacyAwsPullPartialError, LegacyAwsPullService


class Config:
    def __init__(self, **values):
        self.values = {
            "AWS_LEGACY_PULL_ACCESS_KEY_ID": "aws-key",
            "AWS_LEGACY_PULL_SECRET_ACCESS_KEY": "aws-secret",
            "AWS_LEGACY_PULL_REGION": "eu-central-1",
            "AWS_LEGACY_PULL_DYNAMODB_TABLE": "legacy-documents",
            "AWS_LEGACY_PULL_S3_BUCKET": "legacy-source",
            "AWS_LEGACY_PULL_OVERLAP_SECONDS": "300",
            **values,
        }

    def get(self, key):
        return self.values.get(key)

    def require(self, key):
        return self.values[key]


class Tracker:
    instances = []

    def __init__(self, *_args):
        self.counts = None
        self.partial = None
        type(self).instances.append(self)

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def set_dates(self, **_kwargs):
        pass

    def set_counts(self, **kwargs):
        self.counts = kwargs

    def mark_partial(self, note):
        self.partial = note


def aws(items):
    table = MagicMock()
    table.query.return_value = {"Items": items}
    session = MagicMock()
    session.resource.return_value.Table.return_value = table
    module = MagicMock()
    module.Session.return_value = session
    return module, session, table


def service(items, monkeypatch, *, config=None):
    Tracker.instances.clear()
    module, aws_session, table = aws(items)
    monkeypatch.setattr("library.legacy_aws_pull_service.ImportLogTracker", Tracker)
    database = MagicMock()
    database.scalar.return_value = None
    instance = LegacyAwsPullService(database, MagicMock(), config or Config(), boto3_module=module,
                                    now=lambda: datetime(2026, 7, 20, 12, tzinfo=timezone.utc))
    monkeypatch.setattr(instance, "_query_items", MagicMock(return_value=items))
    return instance, aws_session, table


def test_dynamodb_query_paginates(monkeypatch):
    # boto3 is installed for the backend runtime; only the Key expression is irrelevant here.
    import library.legacy_aws_pull_service as module

    table = MagicMock()
    table.query.side_effect = [
        {"Items": [{"created_at": "2026-07-20T00:00:00Z"}], "LastEvaluatedKey": {"id": "next"}},
        {"Items": [{"created_at": "2026-07-20T00:00:01Z"}]},
    ]
    instance = LegacyAwsPullService(None, None, Config())
    monkeypatch.setattr(module, "datetime", datetime)
    items = instance._query_items(table, datetime(2026, 7, 20, tzinfo=timezone.utc), datetime(2026, 7, 20, 1, tzinfo=timezone.utc))
    assert len(items) == 2
    assert table.query.call_count == 2
    assert table.query.call_args_list[1].kwargs["ExclusiveStartKey"] == {"id": "next"}


def test_watermark_overlap_and_empty_full_success(monkeypatch):
    instance, _aws_session, _table = service([], monkeypatch)
    result = instance.run({"since": "2026-07-20T10:00:00Z", "limit": 0, "dry_run": False})
    assert result["found"] == 0
    assert result["query_since"] == "2026-07-20T09:55:00+00:00"
    assert Tracker.instances[0].partial is None


def test_partial_failure_does_not_finish_successfully(monkeypatch):
    instance, aws_session, _table = service([{"uuid": "u", "url": "https://example.test"}], monkeypatch)
    aws_session.client.return_value.get_object.side_effect = RuntimeError("S3 unavailable")
    with pytest.raises(LegacyAwsPullPartialError):
        instance.run({"since": "2026-07-20T10:00:00Z"})
    assert Tracker.instances[0].partial == "one or more items failed"


def test_partial_failure_logs_item_identity_and_exception(monkeypatch, caplog):
    item = {"uuid": "broken-uuid", "url": "https://example.test/broken"}
    instance, aws_session, _table = service([item], monkeypatch)
    aws_session.client.return_value.get_object.side_effect = RuntimeError("S3 unavailable")

    with pytest.raises(LegacyAwsPullPartialError), caplog.at_level("ERROR", logger="library.legacy_aws_pull_service"):
        instance.run({"since": "2026-07-20T10:00:00Z"})

    assert "legacy AWS item failed uuid=broken-uuid url=https://example.test/broken" in caplog.text
    assert "RuntimeError: S3 unavailable" in caplog.text


def test_limit_marks_import_partial_without_advancing_watermark(monkeypatch):
    instance, aws_session, _table = service([{"uuid": "u", "url": "https://example.test"}], monkeypatch)
    aws_session.client.return_value.get_object.side_effect = [
        {"Body": MagicMock(read=lambda: b"text")}, {"Body": MagicMock(read=lambda: b"<html>")},
    ]
    ingest = MagicMock()
    ingest.ingest.return_value = MagicMock(status="added", processing_job_id="document-job")
    monkeypatch.setattr("library.legacy_aws_pull_service.DocumentIngestService", MagicMock(return_value=ingest))
    instance.run({"since": "2026-07-20T10:00:00Z", "limit": 1})
    assert Tracker.instances[0].partial == "diagnostic limit"


def test_existing_local_document_skips_s3_and_ingest(monkeypatch):
    instance, aws_session, _table = service(
        [{"s3_uuid": "local-uuid", "url": "https://example.test/local", "type": "social_media_post"}],
        monkeypatch,
    )
    instance.session.scalar.side_effect = [None, 9340]
    ingest_factory = MagicMock()
    monkeypatch.setattr("library.legacy_aws_pull_service.DocumentIngestService", ingest_factory)

    result = instance.run({"since": "2026-07-20T10:00:00Z"})

    assert result["skipped"] == 1
    aws_session.client.assert_not_called()
    ingest_factory.return_value.ingest.assert_not_called()


def test_dry_run_neither_reads_database_nor_minio(monkeypatch):
    module, _aws_session, _table = aws([{"uuid": "u", "url": "https://example.test"}])
    db = MagicMock()
    storage = MagicMock()
    instance = LegacyAwsPullService(db, storage, Config(), boto3_module=module,
                                    now=lambda: datetime(2026, 7, 20, tzinfo=timezone.utc))
    monkeypatch.setattr(instance, "_query_items", MagicMock(return_value=[]))
    instance.run({"since": "2026-07-20T10:00:00Z", "dry_run": True})
    db.scalar.assert_not_called()
    storage.method_calls == []
    module.Session.return_value.client.assert_not_called()


def test_aws_session_uses_explicit_aws_credentials_not_minio_credentials():
    module = MagicMock()
    config = Config(STORAGE_ACCESS_KEY="minio-key", STORAGE_SECRET_KEY="minio-secret", AWS_LEGACY_PULL_SESSION_TOKEN="token")
    LegacyAwsPullService(None, None, config, boto3_module=module)._aws_session()
    assert module.Session.call_args.kwargs == {
        "aws_access_key_id": "aws-key", "aws_secret_access_key": "aws-secret",
        "region_name": "eu-central-1", "aws_session_token": "token",
    }


def test_create_duplicate_and_fill_missing_html_enqueue_document_jobs(monkeypatch):
    items = [
        {"uuid": "create", "url": "https://example.test/create", "type": "webpage"},
        {"uuid": "duplicate", "url": "https://example.test/duplicate", "type": "webpage"},
        {"uuid": "fill", "url": "https://example.test/fill", "type": "webpage", "target_document_id": 12},
    ]
    instance, aws_session, _table = service(items, monkeypatch)
    aws_session.client.return_value.get_object.side_effect = [
        {"Body": MagicMock(read=lambda: b"text")}, {"Body": MagicMock(read=lambda: b"<html>")},
    ] * 3
    ingest = MagicMock()
    ingest.ingest.side_effect = [MagicMock(status="added", processing_job_id="a"), MagicMock(status="already_exists", processing_job_id="b"), MagicMock(status="refreshed", processing_job_id="c")]
    monkeypatch.setattr("library.legacy_aws_pull_service.DocumentIngestService", MagicMock(return_value=ingest))
    result = instance.run({"since": "2026-07-20T10:00:00Z"})
    assert result["added"] == result["skipped"] == result["refreshed"] == 1
    assert ingest.ingest.call_args_list[2].args[0].operation == "fill_missing_html"
    assert all(call.args[0].document_type == "webpage" for call in ingest.ingest.call_args_list)


def test_jobs_api_accepts_only_documented_bridge_parameters(monkeypatch):
    from library.feed_routes import create_job

    app = Flask(__name__)
    session = MagicMock()
    queued = MagicMock(id="bridge-job", status="queued")
    monkeypatch.setattr("library.feed_routes.get_scoped_session", lambda: session)
    monkeypatch.setattr("library.feed_routes.enqueue", MagicMock(return_value=queued))
    with app.test_request_context("/jobs", method="POST", json={"type": "legacy_aws_pull", "parameters": {"since": "2026-07-20T00:00:00Z", "dry_run": True, "limit": 1}}):
        g.auth = MagicMock(kind="service")
        response, status = create_job()
        assert status == 202
        assert response.json == {"id": "bridge-job", "status": "queued"}
    with app.test_request_context("/jobs", method="POST", json={"type": "legacy_aws_pull", "parameters": {"bucket": "forbidden"}}):
        g.auth = MagicMock(kind="service")
        with pytest.raises(BadRequest):
            create_job()
