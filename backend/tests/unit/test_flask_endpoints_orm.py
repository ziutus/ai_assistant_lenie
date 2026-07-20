"""Unit tests for Flask endpoints migrated to ORM (Story 27.3).

Tests verify that Flask route handlers correctly use ORM models and scoped sessions
while preserving the exact API response formats expected by the frontend.
"""

from unittest.mock import ANY, MagicMock, patch

import pytest

sa = pytest.importorskip("sqlalchemy")

# Headers sent with every request (auth is mocked in fixture, but headers don't hurt)
API_HEADERS = {"x-api-key": "test-api-key"}


@pytest.fixture()
def client():
    """Create Flask test client with auth bypassed.

    Auth is bypassed by mocking check_auth_header — the real config may
    load secrets from Vault/AWS SSM, making env patching insufficient.
    """
    import server
    server.app.config["TESTING"] = True
    with patch.object(server, "check_auth_header"):
        with server.app.test_client() as c:
            yield c


# ---------------------------------------------------------------------------
# /website_list
# ---------------------------------------------------------------------------


class TestWebsiteList:
    def test_returns_correct_format(self, client):
        mock_list = [{"id": 1, "url": "https://example.com", "title": "Test",
                       "document_type": "webpage", "ingested_at": "2026-03-09 10:30:45",
                       "processing_status": "URL_ADDED", "processing_error_code": "NONE",
                       "note": None, "collection_id": None, "uuid": None}]
        mock_session = MagicMock()
        with patch("server.get_scoped_session", return_value=mock_session):
            with patch("server.DocumentRepository") as MockRepo:
                repo_instance = MagicMock()
                repo_instance.get_list.side_effect = lambda **kw: 1 if kw.get("count") else mock_list
                MockRepo.return_value = repo_instance

                resp = client.get("/website_list?type=webpage", headers=API_HEADERS)

        assert resp.status_code == 200
        data = resp.get_json()
        assert data["status"] == "success"
        assert data["message"] == "Dane odczytane pomyślnie."
        assert data["encoding"] == "utf8"
        assert "websites" in data
        assert data["all_results_count"] == 1

    def test_passes_query_params(self, client):
        mock_session = MagicMock()
        with patch("server.get_scoped_session", return_value=mock_session):
            with patch("server.DocumentRepository") as MockRepo:
                repo_instance = MagicMock()
                repo_instance.get_list.return_value = []
                MockRepo.return_value = repo_instance

                client.get(
                    "/website_list?type=link&processing_status=URL_ADDED&search_in_document=test",
                    headers=API_HEADERS,
                )

                calls = repo_instance.get_list.call_args_list
                assert len(calls) == 2
                assert calls[0].kwargs["document_type"] == "link"
                assert calls[0].kwargs["processing_status"] == "URL_ADDED"
                assert calls[0].kwargs["search_in_documents"] == "test"


# ---------------------------------------------------------------------------
# /website_count
# ---------------------------------------------------------------------------


class TestWebsiteCount:
    def test_returns_correct_format(self, client):
        mock_counts = {"webpage": 10, "link": 5, "ALL": 15}
        mock_session = MagicMock()
        with patch("server.get_scoped_session", return_value=mock_session):
            with patch("server.DocumentRepository") as MockRepo:
                repo_instance = MagicMock()
                repo_instance.get_count_by_type.return_value = mock_counts
                MockRepo.return_value = repo_instance

                resp = client.get("/website_count", headers=API_HEADERS)

        assert resp.status_code == 200
        data = resp.get_json()
        assert data["status"] == "success"
        assert data["counts"] == mock_counts


# ---------------------------------------------------------------------------
# /website_get
# ---------------------------------------------------------------------------


class TestWebsiteGet:
    def test_found_with_reach(self, client):
        mock_doc = MagicMock()
        mock_doc.dict.return_value = {
            "id": 42, "url": "https://example.com", "title": "Test Doc",
            "next_id": 43, "next_type": "link", "previous_id": 41, "previous_type": "webpage",
            "summary": None, "language": "en", "tags": None, "text": "content",
            "paywall": False, "ingested_at": "2026-03-09 10:00:00",
            "document_type": "webpage", "source": None, "published_on": None,
            "original_id": None, "document_length": None, "chapter_list": None,
            "processing_status": "URL_ADDED", "processing_error_code": "NONE",
            "text_raw": None, "transcript_job_id": None, "ai_summary_needed": False,
            "byline": None, "note": None, "uuid": None, "collection_id": None,
            "text_md": None, "transcript_needed": False,
        }
        mock_session = MagicMock()
        mock_session.execute.return_value.scalar.return_value = 0  # embeddings/chunks counts
        with patch("server.get_scoped_session", return_value=mock_session):
            with patch("server.DocumentService") as MockDS:
                mock_service = MagicMock()
                mock_service.get_document.return_value = mock_doc
                MockDS.return_value = mock_service

                resp = client.get("/website_get?id=42", headers=API_HEADERS)

        assert resp.status_code == 200
        data = resp.get_json()
        assert data["id"] == 42
        assert data["next_id"] == 43
        assert data["embeddings_count"] == 0
        assert data["approved_chunks_count"] == 0
        mock_service.get_document.assert_called_once_with(42)

    def test_not_found_returns_404(self, client):
        mock_session = MagicMock()
        with patch("server.get_scoped_session", return_value=mock_session):
            with patch("server.DocumentService") as MockDS:
                mock_service = MagicMock()
                mock_service.get_document.return_value = None
                MockDS.return_value = mock_service

                resp = client.get("/website_get?id=999", headers=API_HEADERS)

        assert resp.status_code == 404
        data = resp.get_json()
        assert data["status"] == "error"
        assert data["message"] == "Document not found"

    def test_missing_id_returns_400(self, client):
        resp = client.get("/website_get", headers=API_HEADERS)
        assert resp.status_code == 400


# ---------------------------------------------------------------------------
# /website_get_next_to_correct
# ---------------------------------------------------------------------------


class TestWebsiteGetNextToCorrect:
    def test_found(self, client):
        mock_session = MagicMock()
        with patch("server.get_scoped_session", return_value=mock_session):
            with patch("server.DocumentRepository") as MockRepo:
                repo_instance = MagicMock()
                repo_instance.get_next_to_correct.return_value = (43, "link")
                MockRepo.return_value = repo_instance

                resp = client.get("/website_get_next_to_correct?id=42", headers=API_HEADERS)

        assert resp.status_code == 200
        data = resp.get_json()
        assert data["status"] == "success"
        assert data["next_id"] == 43
        assert data["next_type"] == "link"

    def test_not_found_returns_minus_one(self, client):
        mock_session = MagicMock()
        with patch("server.get_scoped_session", return_value=mock_session):
            with patch("server.DocumentRepository") as MockRepo:
                repo_instance = MagicMock()
                repo_instance.get_next_to_correct.return_value = -1
                MockRepo.return_value = repo_instance

                resp = client.get("/website_get_next_to_correct?id=9999", headers=API_HEADERS)

        assert resp.status_code == 200
        data = resp.get_json()
        assert data["next_id"] == -1
        assert data["next_type"] == ""


# ---------------------------------------------------------------------------
# /website_delete
# ---------------------------------------------------------------------------


class TestWebsiteDelete:
    def test_delete_existing(self, client):
        mock_session = MagicMock()
        with patch("server.get_scoped_session", return_value=mock_session):
            with patch("server.DocumentService") as MockDS:
                mock_service = MagicMock()
                mock_service.delete_document.return_value = True
                MockDS.return_value = mock_service

                resp = client.get("/website_delete?id=42", headers=API_HEADERS)

        assert resp.status_code == 200
        data = resp.get_json()
        assert data["status"] == "success"
        assert data["message"] == "Page has been deleted from database"
        mock_service.delete_document.assert_called_once_with(42)

    def test_delete_nonexistent(self, client):
        mock_session = MagicMock()
        with patch("server.get_scoped_session", return_value=mock_session):
            with patch("server.DocumentService") as MockDS:
                mock_service = MagicMock()
                mock_service.delete_document.return_value = False
                MockDS.return_value = mock_service

                resp = client.get("/website_delete?id=999", headers=API_HEADERS)

        assert resp.status_code == 200
        data = resp.get_json()
        assert data["message"] == "Page doesn't exist in database"

    def test_delete_error_rollback(self, client):
        mock_session = MagicMock()
        with patch("server.get_scoped_session", return_value=mock_session):
            with patch("server.DocumentService") as MockDS:
                mock_service = MagicMock()
                mock_service.delete_document.side_effect = Exception("DB constraint error")
                MockDS.return_value = mock_service

                resp = client.get("/website_delete?id=42", headers=API_HEADERS)

        assert resp.status_code == 500
        data = resp.get_json()
        assert data["status"] == "error"

    def test_delete_missing_id_returns_400(self, client):
        resp = client.get("/website_delete", headers=API_HEADERS)
        assert resp.status_code == 400


# ---------------------------------------------------------------------------
# /website_similar — removed in stage 12 (POST /search is the only search
# endpoint); pin the removal so a stray revert is caught.
# ---------------------------------------------------------------------------


class TestWebsiteSimilarRemoved:
    def test_endpoint_is_gone(self, client):
        resp = client.post("/website_similar", json={"search": "x"}, headers=API_HEADERS)
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# /ai_get_embedding
# ---------------------------------------------------------------------------


class TestAiGetEmbedding:
    def test_search_service_used(self, client):
        """Verify /ai_get_embedding delegates to SearchService."""
        mock_embedding = {"text": "test text", "embedding": [0.1, 0.2], "status": "success"}
        mock_session = MagicMock()
        with patch("server.get_scoped_session", return_value=mock_session):
            with patch("server.SearchService") as MockService:
                service_instance = MagicMock()
                service_instance.get_embedding.return_value = mock_embedding
                MockService.return_value = service_instance

                resp = client.post("/ai_get_embedding", json={
                    "search": "test text",
                }, headers=API_HEADERS, content_type="application/json")

        assert resp.status_code == 200
        data = resp.get_json()
        assert data["status"] == "success"
        assert data["text"] == "test text"
        MockService.assert_called_once_with(mock_session)
        service_instance.get_embedding.assert_called_once_with("test text")

    def test_error_returns_500(self, client):
        """Verify /ai_get_embedding returns 500 when embedding generation fails."""
        mock_session = MagicMock()
        with patch("server.get_scoped_session", return_value=mock_session):
            with patch("server.SearchService") as MockService:
                service_instance = MagicMock()
                service_instance.get_embedding.side_effect = RuntimeError("API connection failed")
                MockService.return_value = service_instance

                resp = client.post("/ai_get_embedding", json={
                    "search": "test text",
                }, headers=API_HEADERS, content_type="application/json")

        assert resp.status_code == 500
        data = resp.get_json()
        assert data["status"] == "error"
        # Generic message — internal error details are logged, not leaked to the client
        assert data["message"] == "Error generating embedding"
        assert "API connection failed" not in data["message"]

    def test_form_data_accepted(self, client):
        """Verify /ai_get_embedding accepts form data input."""
        mock_embedding = {"text": "form text", "embedding": [0.1], "status": "success"}
        mock_session = MagicMock()
        with patch("server.get_scoped_session", return_value=mock_session):
            with patch("server.SearchService") as MockService:
                service_instance = MagicMock()
                service_instance.get_embedding.return_value = mock_embedding
                MockService.return_value = service_instance

                resp = client.post("/ai_get_embedding", data={
                    "search": "form text",
                }, headers=API_HEADERS)

        assert resp.status_code == 200
        service_instance.get_embedding.assert_called_once_with("form text")


# ---------------------------------------------------------------------------
# /website_save
# ---------------------------------------------------------------------------


class TestWebsiteSave:
    def test_update_existing_doc(self, client):
        mock_doc = MagicMock()
        mock_doc.id = 42
        mock_session = MagicMock()
        with patch("server.get_scoped_session", return_value=mock_session):
            with patch("server.DocumentService") as MockDS:
                mock_service = MagicMock()
                mock_service.save_document.return_value = mock_doc
                MockDS.return_value = mock_service

                resp = client.post("/website_save", data={
                    "url": "https://example.com",
                    "id": "42",
                    "processing_status": "URL_ADDED",
                    "document_type": "webpage",
                    "text": "new text",
                    "title": "New Title",
                }, headers=API_HEADERS)

        assert resp.status_code == 200
        data = resp.get_json()
        assert data["status"] == "success"
        assert "42" in data["message"]
        mock_service.save_document.assert_called_once()

    def test_create_new_doc(self, client):
        mock_doc = MagicMock()
        mock_doc.id = 100
        mock_session = MagicMock()
        with patch("server.get_scoped_session", return_value=mock_session):
            with patch("server.DocumentService") as MockDS:
                mock_service = MagicMock()
                mock_service.save_document.return_value = mock_doc
                MockDS.return_value = mock_service

                resp = client.post("/website_save", data={
                    "url": "https://new.example.com",
                    "id": "999",
                    "processing_status": "URL_ADDED",
                    "document_type": "link",
                    "title": "New Link",
                }, headers=API_HEADERS)

        assert resp.status_code == 200
        mock_service.save_document.assert_called_once()

    def test_error_handling(self, client):
        mock_session = MagicMock()
        with patch("server.get_scoped_session", return_value=mock_session):
            with patch("server.DocumentService") as MockDS:
                mock_service = MagicMock()
                mock_service.save_document.side_effect = Exception("DB error")
                MockDS.return_value = mock_service

                resp = client.post("/website_save", data={
                    "url": "https://example.com",
                    "id": "42",
                    "processing_status": "URL_ADDED",
                    "document_type": "webpage",
                }, headers=API_HEADERS)

        assert resp.status_code == 500
        data = resp.get_json()
        assert data["status"] == "error"
        mock_session.rollback.assert_called_once()

    def test_missing_url_returns_400(self, client):
        resp = client.post("/website_save", data={}, headers=API_HEADERS)
        assert resp.status_code == 400

    def test_only_sets_provided_attributes(self, client):
        mock_doc = MagicMock()
        mock_doc.id = 42
        mock_session = MagicMock()
        with patch("server.get_scoped_session", return_value=mock_session):
            with patch("server.DocumentService") as MockDS:
                mock_service = MagicMock()
                mock_service.save_document.return_value = mock_doc
                MockDS.return_value = mock_service

                resp = client.post("/website_save", data={
                    "url": "https://example.com",
                    "id": "42",
                    "processing_status": "URL_ADDED",
                    "document_type": "webpage",
                    "title": "Updated Title",
                    # 'text' is intentionally NOT submitted
                }, headers=API_HEADERS)

        assert resp.status_code == 200
        # Verify save_document was called with only provided attributes
        call_kwargs = mock_service.save_document.call_args
        assert "text" not in call_kwargs.kwargs


# ---------------------------------------------------------------------------
# /url_add
# ---------------------------------------------------------------------------


class TestUrlAdd:
    def test_duplicate_returns_existing_document_details(self, client):
        from library.document_service import ExistingDocumentError

        mock_session = MagicMock()
        existing = MagicMock()
        existing.id = 77
        existing.text_raw = "<html>stored</html>"
        with patch("server.get_scoped_session", return_value=mock_session), \
             patch("server.DocumentService") as MockDS:
            MockDS.return_value.create_document.side_effect = ExistingDocumentError(existing)
            resp = client.post("/url_add", json={
                "url": "https://example.com", "type": "webpage", "html": "<html>new</html>",
            }, headers=API_HEADERS, content_type="application/json")

        assert resp.status_code == 409
        assert resp.get_json() == {
            "status": "already_exists",
            "message": "Document already exists with ID: 77",
            "document_id": 77,
            "missing_raw_html": False,
        }

    def test_successful_add(self, client):
        mock_session = MagicMock()
        mock_doc = MagicMock()
        mock_doc.id = 100
        with patch("server.get_scoped_session", return_value=mock_session):
            with patch("server.DocumentService") as MockDS:
                mock_service = MagicMock()
                mock_service.create_document.return_value = mock_doc
                MockDS.return_value = mock_service

                resp = client.post("/url_add", json={
                    "url": "https://example.com",
                    "type": "link",
                    "title": "Test Link",
                }, headers=API_HEADERS, content_type="application/json")

        assert resp.status_code == 200
        data = resp.get_json()
        assert data["status"] == "success"
        assert data["document_id"] == 100
        mock_service.create_document.assert_called_once()

    def test_missing_required_params(self, client):
        mock_session = MagicMock()
        with patch("server.get_scoped_session", return_value=mock_session):
            with patch("server.DocumentService") as MockDS:
                mock_service = MagicMock()
                mock_service.create_document.side_effect = ValueError("Missing required parameter(s): 'url' or 'type'")
                MockDS.return_value = mock_service

                resp = client.post("/url_add", json={"url": "https://example.com"},
                                   headers=API_HEADERS, content_type="application/json")
        assert resp.status_code == 400
        data = resp.get_json()
        # Generic message — validation details are logged, not leaked to the client
        assert data["message"] == "Invalid request data"
        assert "Missing required" not in data["message"]

    def test_add_link_type(self, client):
        """Verify url_add for link type succeeds (no S3 upload for links)."""
        mock_session = MagicMock()
        mock_doc = MagicMock()
        mock_doc.id = 101
        with patch("server.get_scoped_session", return_value=mock_session):
            with patch("server.DocumentService") as MockDS:
                mock_service = MagicMock()
                mock_service.create_document.return_value = mock_doc
                MockDS.return_value = mock_service

                resp = client.post("/url_add", json={
                    "url": "https://example.com/article",
                    "type": "link",
                    "title": "An Article",
                    "source": "manual",
                }, headers=API_HEADERS, content_type="application/json")

        assert resp.status_code == 200
        data = resp.get_json()
        assert data["status"] == "success"
        mock_service.create_document.assert_called_once()


# ---------------------------------------------------------------------------
# /website_youtube_retry_captions
# ---------------------------------------------------------------------------


class TestWebsiteYoutubeRetryCaptions:
    def _mock_doc(self, document_type="youtube", processing_status="TEMPORARY_ERROR"):
        mock_doc = MagicMock()
        mock_doc.id = 9163
        mock_doc.url = "https://www.youtube.com/watch?v=abc123"
        mock_doc.document_type = document_type
        mock_doc.processing_status = processing_status
        mock_doc.language = "pl"
        mock_doc.chapter_list = None
        mock_doc.note = None
        mock_doc.discovery_source_name = "own"
        return mock_doc

    def test_retries_when_no_transcript_yet(self, client):
        mock_session = MagicMock()
        mock_doc = self._mock_doc()
        updated_doc = self._mock_doc(processing_status="NEED_MANUAL_REVIEW")
        updated_doc.processing_error_code = "NONE"
        with patch("server.get_scoped_session", return_value=mock_session):
            with patch("server.DocumentService") as MockDS:
                mock_service = MagicMock()
                mock_service.get_document.return_value = mock_doc
                MockDS.return_value = mock_service
                with patch("server.process_youtube_url", return_value=updated_doc) as mock_process:
                    resp = client.post("/website_youtube_retry_captions", data={"id": "9163"}, headers=API_HEADERS)

        assert resp.status_code == 200
        data = resp.get_json()
        assert data["status"] == "success"
        assert data["processing_status"] == "NEED_MANUAL_REVIEW"
        mock_process.assert_called_once_with(
            session=mock_session,
            youtube_url=mock_doc.url,
            language=mock_doc.language,
            chapter_list=mock_doc.chapter_list,
            note=mock_doc.note,
            source=mock_doc.discovery_source_name,
            webshare_api_key=ANY,
        )

    def test_rejects_non_youtube_document(self, client):
        mock_session = MagicMock()
        mock_doc = self._mock_doc(document_type="webpage")
        with patch("server.get_scoped_session", return_value=mock_session):
            with patch("server.DocumentService") as MockDS:
                mock_service = MagicMock()
                mock_service.get_document.return_value = mock_doc
                MockDS.return_value = mock_service

                resp = client.post("/website_youtube_retry_captions", data={"id": "9163"}, headers=API_HEADERS)

        assert resp.status_code == 400

    def test_rejects_when_transcript_already_exists(self, client):
        """A document already past NEED_TRANSCRIPTION has a transcript — retry
        must not risk overwriting reviewed text."""
        mock_session = MagicMock()
        mock_doc = self._mock_doc(processing_status="NEED_MANUAL_REVIEW")
        with patch("server.get_scoped_session", return_value=mock_session):
            with patch("server.DocumentService") as MockDS:
                mock_service = MagicMock()
                mock_service.get_document.return_value = mock_doc
                MockDS.return_value = mock_service
                with patch("server.process_youtube_url") as mock_process:
                    resp = client.post("/website_youtube_retry_captions", data={"id": "9163"}, headers=API_HEADERS)

        assert resp.status_code == 409
        mock_process.assert_not_called()

    def test_not_found_returns_404(self, client):
        mock_session = MagicMock()
        with patch("server.get_scoped_session", return_value=mock_session):
            with patch("server.DocumentService") as MockDS:
                mock_service = MagicMock()
                mock_service.get_document.return_value = None
                MockDS.return_value = mock_service

                resp = client.post("/website_youtube_retry_captions", data={"id": "999"}, headers=API_HEADERS)

        assert resp.status_code == 404

    def test_missing_id_returns_400(self, client):
        resp = client.post("/website_youtube_retry_captions", data={}, headers=API_HEADERS)
        assert resp.status_code == 400
