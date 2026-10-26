"""Channel-name fallback for YouTube documents (oEmbed) and its use in process_youtube_url()."""

import sys
from types import ModuleType, SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

requests = pytest.importorskip("requests")
pytest.importorskip("sqlalchemy")

for _mod_name in ["boto3", "boto3.dynamodb", "boto3.dynamodb.conditions", "botocore",
                  "botocore.exceptions", "botocore.compat", "s3transfer"]:
    if _mod_name not in sys.modules:
        _mock_mod = MagicMock(spec=ModuleType)
        if _mod_name == "botocore.exceptions":
            _mock_mod.ClientError = type("ClientError", (Exception,), {})
        sys.modules[_mod_name] = _mock_mod

from library.youtube_oembed import fetch_channel_name  # noqa: E402

VIDEO_URL = "https://www.youtube.com/watch?v=oPYJlnigePg"


def _response(status=200, payload=None, json_error=False):
    response = MagicMock()
    response.status_code = status
    if json_error:
        response.json.side_effect = ValueError("not json")
    else:
        response.json.return_value = payload
    return response


class TestFetchChannelName:
    def test_returns_author_name(self):
        payload = {"author_name": " Mateusz Chrobok ", "title": "x"}
        with patch("library.youtube_oembed.requests.get", return_value=_response(payload=payload)) as get:
            assert fetch_channel_name(VIDEO_URL) == "Mateusz Chrobok"
        assert get.call_args.kwargs["params"] == {"url": VIDEO_URL, "format": "json"}
        assert get.call_args.kwargs["timeout"] > 0

    @pytest.mark.parametrize("payload", [{}, {"author_name": ""}, {"author_name": "  "}, {"author_name": 5}, []])
    def test_missing_or_blank_name_is_none(self, payload):
        with patch("library.youtube_oembed.requests.get", return_value=_response(payload=payload)):
            assert fetch_channel_name(VIDEO_URL) is None

    def test_http_error_is_none(self):
        with patch("library.youtube_oembed.requests.get", return_value=_response(status=401)):
            assert fetch_channel_name(VIDEO_URL) is None

    def test_invalid_json_is_none(self):
        with patch("library.youtube_oembed.requests.get", return_value=_response(json_error=True)):
            assert fetch_channel_name(VIDEO_URL) is None

    def test_network_error_is_none(self):
        with patch("library.youtube_oembed.requests.get", side_effect=requests.ConnectionError("down")):
            assert fetch_channel_name(VIDEO_URL) is None


def _process(monkeypatch, tmp_path, byline, channel):
    from library import youtube_processing as yt
    from library.db.models import Document

    doc = Document(id=11178, url=VIDEO_URL, document_type="youtube", processing_status="NEED_TRANSCRIPTION",
                   language="pl", byline=byline, title="Title from the feed", transcript_needed=True)
    monkeypatch.setattr(Document, "get_by_url", lambda session, url: doc)
    monkeypatch.setattr(yt, "load_config", lambda: {"CACHE_DIR": str(tmp_path)})
    monkeypatch.setattr(yt, "StalkerYoutubeFile", lambda **kwargs: SimpleNamespace(
        valid=True, metadata_available=False, video_id="oPYJlnigePg", length_seconds=120, length_minutes=2,
        description="", path="unused",
    ))
    ytt = MagicMock()
    ytt.list.return_value = [SimpleNamespace(language_code="pl")]
    ytt.fetch.return_value.to_raw_data.return_value = [{"text": "tekst", "start": 0, "duration": 1}]
    monkeypatch.setattr(yt, "YouTubeTranscriptApi", lambda: ytt)
    monkeypatch.setattr(yt, "text_language_detect", lambda text: "pl")
    monkeypatch.setattr(yt, "compare_language", lambda *args: True)
    monkeypatch.setattr(yt, "youtube_titles_to_text", lambda text: "tekst")
    from library import transcript_corrections
    monkeypatch.setattr(transcript_corrections, "load_active_rules", lambda **kwargs: [])
    monkeypatch.setattr(transcript_corrections, "_bump_hit_counts", MagicMock())
    fetch = MagicMock(return_value=channel)
    monkeypatch.setattr(yt, "fetch_channel_name", fetch)
    yt.process_youtube_url(MagicMock(), VIDEO_URL, cache_dir=str(tmp_path))
    return doc, fetch


class TestProcessUsesChannelFallback:
    def test_empty_byline_is_filled_from_oembed(self, monkeypatch, tmp_path):
        doc, fetch = _process(monkeypatch, tmp_path, byline=None, channel="Mateusz Chrobok")
        assert doc.byline == "Mateusz Chrobok"
        fetch.assert_called_once_with(VIDEO_URL)

    def test_existing_byline_is_kept_without_a_request(self, monkeypatch, tmp_path):
        doc, fetch = _process(monkeypatch, tmp_path, byline="Kanał z feedu", channel="Mateusz Chrobok")
        assert doc.byline == "Kanał z feedu"
        fetch.assert_not_called()

    def test_failed_lookup_leaves_byline_empty(self, monkeypatch, tmp_path):
        doc, _ = _process(monkeypatch, tmp_path, byline="", channel=None)
        assert not doc.byline
