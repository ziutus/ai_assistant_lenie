"""Unit tests for Flask endpoints migrated to ORM (Story 27.3).

Tests verify that Flask route handlers correctly use ORM models and scoped sessions
while preserving the exact API response formats expected by the frontend.
"""

from unittest.mock import MagicMock, patch

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
                       "document_type": "webpage", "created_at": "2026-03-09 10:30:45",
                       "document_state": "URL_ADDED", "document_state_error": "NONE",
                       "note": None, "project": None, "s3_uuid": None}]
        mock_session = MagicMock()
        with patch("server.get_scoped_session", return_value=mock_session):
            with patch("server.WebsitesDBPostgreSQL") as MockRepo:
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
            with patch("server.WebsitesDBPostgreSQL") as MockRepo:
                repo_instance = MagicMock()
                repo_instance.get_list.return_value = []
                MockRepo.return_value = repo_instance

                client.get(
                    "/website_list?type=link&document_state=URL_ADDED&search_in_document=test",
                    headers=API_HEADERS,
                )

                calls = repo_instance.get_list.call_args_list
                assert len(calls) == 2
                assert calls[0].kwargs["document_type"] == "link"
                assert calls[0].kwargs["document_state"] == "URL_ADDED"
                assert calls[0].kwargs["search_in_documents"] == "test"


# ---------------------------------------------------------------------------
# /website_count
# ---------------------------------------------------------------------------


class TestWebsiteCount:
    def test_returns_correct_format(self, client):
        mock_counts = {"webpage": 10, "link": 5, "ALL": 15}
        mock_session = MagicMock()
        with patch("server.get_scoped_session", return_value=mock_session):
            with patch("server.WebsitesDBPostgreSQL") as MockRepo:
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
            "paywall": False, "created_at": "2026-03-09 10:00:00",
            "document_type": "webpage", "source": None, "date_from": None,
            "original_id": None, "document_length": None, "chapter_list": None,
            "document_state": "URL_ADDED", "document_state_error": "NONE",
            "text_raw": None, "transcript_job_id": None, "ai_summary_needed": False,
            "author": None, "note": None, "s3_uuid": None, "project": None,
            "text_md": None, "transcript_needed": False,
        }
        mock_session = MagicMock()
        with patch("server.get_scoped_session", return_value=mock_session):
            with patch("server.WebDocument") as MockWD:
                MockWD.get_by_id.return_value = mock_doc

                resp = client.get("/website_get?id=42", headers=API_HEADERS)

        assert resp.status_code == 200
        data = resp.get_json()
        assert data["id"] == 42
        assert data["next_id"] == 43
        MockWD.get_by_id.assert_called_once_with(mock_session, 42, reach=True)

    def test_not_found_returns_404(self, client):
        mock_session = MagicMock()
        with patch("server.get_scoped_session", return_value=mock_session):
            with patch("server.WebDocument") as MockWD:
                MockWD.get_by_id.return_value = None

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
            with patch("server.WebsitesDBPostgreSQL") as MockRepo:
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
            with patch("server.WebsitesDBPostgreSQL") as MockRepo:
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
        mock_doc = MagicMock()
        mock_session = MagicMock()
        with patch("server.get_scoped_session", return_value=mock_session):
            with patch("server.WebDocument") as MockWD:
                MockWD.get_by_id.return_value = mock_doc

                resp = client.get("/website_delete?id=42", headers=API_HEADERS)

        assert resp.status_code == 200
        data = resp.get_json()
        assert data["status"] == "success"
        assert data["message"] == "Page has been deleted from database"
        mock_session.delete.assert_called_once_with(mock_doc)
        mock_session.commit.assert_called_once()

    def test_delete_nonexistent(self, client):
        mock_session = MagicMock()
        with patch("server.get_scoped_session", return_value=mock_session):
            with patch("server.WebDocument") as MockWD:
                MockWD.get_by_id.return_value = None

                resp = client.get("/website_delete?id=999", headers=API_HEADERS)

        assert resp.status_code == 200
        data = resp.get_json()
        assert data["message"] == "Page doesn't exist in database"
        mock_session.delete.assert_not_called()

    def test_delete_error_rollback(self, client):
        mock_doc = MagicMock()
        mock_session = MagicMock()
        mock_session.commit.side_effect = Exception("DB constraint error")
        with patch("server.get_scoped_session", return_value=mock_session):
            with patch("server.WebDocument") as MockWD:
                MockWD.get_by_id.return_value = mock_doc

                resp = client.get("/website_delete?id=42", headers=API_HEADERS)

        assert resp.status_code == 500
        data = resp.get_json()
        assert data["status"] == "error"
        mock_session.rollback.assert_called_once()

    def test_delete_missing_id_returns_400(self, client):
        resp = client.get("/website_delete", headers=API_HEADERS)
        assert resp.status_code == 400


# ---------------------------------------------------------------------------
# /website_similar
# ---------------------------------------------------------------------------


class TestWebsiteSimilar:
    def test_orm_session_used(self, client):
        """Verify /website_similar creates WebsitesDBPostgreSQL with ORM session."""
        mock_embedding_result = MagicMock()
        mock_embedding_result.status = "success"
        mock_embedding_result.embedding = [0.1, 0.2, 0.3]

        mock_session = MagicMock()
        with patch("server.get_scoped_session", return_value=mock_session):
            with patch("server.WebsitesDBPostgreSQL") as MockRepo:
                repo_instance = MagicMock()
                repo_instance.get_similar.return_value = [{"website_id": 1, "similarity": 0.9}]
                MockRepo.return_value = repo_instance

                with patch("library.embedding.get_embedding", return_value=mock_embedding_result):
                    resp = client.post("/website_similar", json={
                        "search": "test query",
                        "limit": 5,
                    }, headers=API_HEADERS, content_type="application/json")

        assert resp.status_code == 200
        data = resp.get_json()
        assert data["status"] == "success"
        # ORM instance created with session argument
        MockRepo.assert_called_once_with(session=mock_session)

    def test_returns_correct_json_structure(self, client):
        """Verify endpoint returns status, message, websites keys."""
        mock_embedding_result = MagicMock()
        mock_embedding_result.status = "success"
        mock_embedding_result.embedding = [0.1, 0.2, 0.3]

        mock_session = MagicMock()
        with patch("server.get_scoped_session", return_value=mock_session):
            with patch("server.WebsitesDBPostgreSQL") as MockRepo:
                repo_instance = MagicMock()
                repo_instance.get_similar.return_value = [
                    {"website_id": 1, "text": "t", "similarity": 0.9, "id": 10,
                     "url": "https://example.com", "language": "en", "text_original": "t",
                     "websites_text_length": 100, "embeddings_text_length": 50,
                     "title": "Test", "document_type": "webpage", "project": None}
                ]
                MockRepo.return_value = repo_instance

                with patch("library.embedding.get_embedding", return_value=mock_embedding_result):
                    resp = client.post("/website_similar", json={
                        "search": "test query",
                        "limit": 3,
                    }, headers=API_HEADERS, content_type="application/json")

        assert resp.status_code == 200
        data = resp.get_json()
        assert data["status"] == "success"
        assert "message" in data
        assert "websites" in data
        assert len(data["websites"]) == 1

    def test_limit_cast_to_int(self, client):
        """Verify limit parameter from form/args (string) is cast to int."""
        mock_embedding_result = MagicMock()
        mock_embedding_result.status = "success"
        mock_embedding_result.embedding = [0.1, 0.2, 0.3]

        mock_session = MagicMock()
        with patch("server.get_scoped_session", return_value=mock_session):
            with patch("server.WebsitesDBPostgreSQL") as MockRepo:
                repo_instance = MagicMock()
                repo_instance.get_similar.return_value = []
                MockRepo.return_value = repo_instance

                with patch("library.embedding.get_embedding", return_value=mock_embedding_result):
                    resp = client.post("/website_similar", data={
                        "search": "test query",
                        "limit": "7",
                    }, headers=API_HEADERS)

        assert resp.status_code == 200
        # Verify limit was passed as int, not string
        call_kwargs = repo_instance.get_similar.call_args
        limit_arg = call_kwargs.kwargs.get("limit") or call_kwargs[1].get("limit")
        if limit_arg is None:
            # positional arg: get_similar(embedding, model, limit=...)
            limit_arg = call_kwargs[0][2] if len(call_kwargs[0]) > 2 else None
        assert isinstance(limit_arg, int)
        assert limit_arg == 7


# ---------------------------------------------------------------------------
# /website_save
# ---------------------------------------------------------------------------


class TestWebsiteSave:
    def test_update_existing_doc(self, client):
        mock_doc = MagicMock()
        mock_doc.id = 42
        mock_session = MagicMock()
        with patch("server.get_scoped_session", return_value=mock_session):
            with patch("server.WebDocument") as MockWD:
                MockWD.get_by_id.return_value = mock_doc

                resp = client.post("/website_save", data={
                    "url": "https://example.com",
                    "id": "42",
                    "document_state": "URL_ADDED",
                    "document_type": "webpage",
                    "text": "new text",
                    "title": "New Title",
                }, headers=API_HEADERS)

        assert resp.status_code == 200
        data = resp.get_json()
        assert data["status"] == "success"
        assert "42" in data["message"]
        mock_session.commit.assert_called_once()

    def test_create_new_doc(self, client):
        mock_session = MagicMock()
        with patch("server.get_scoped_session", return_value=mock_session):
            with patch("server.WebDocument") as MockWD:
                MockWD.get_by_id.return_value = None
                MockWD.get_by_url.return_value = None
                new_doc = MagicMock()
                new_doc.id = 100
                MockWD.return_value = new_doc

                resp = client.post("/website_save", data={
                    "url": "https://new.example.com",
                    "id": "999",
                    "document_state": "URL_ADDED",
                    "document_type": "link",
                    "title": "New Link",
                }, headers=API_HEADERS)

        assert resp.status_code == 200
        mock_session.add.assert_called_once_with(new_doc)
        mock_session.commit.assert_called_once()

    def test_error_handling(self, client):
        mock_session = MagicMock()
        mock_session.commit.side_effect = Exception("DB error")
        mock_doc = MagicMock()
        mock_doc.id = 42
        with patch("server.get_scoped_session", return_value=mock_session):
            with patch("server.WebDocument") as MockWD:
                MockWD.get_by_id.return_value = mock_doc

                resp = client.post("/website_save", data={
                    "url": "https://example.com",
                    "id": "42",
                    "document_state": "URL_ADDED",
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
            with patch("server.WebDocument") as MockWD:
                MockWD.get_by_id.return_value = mock_doc

                resp = client.post("/website_save", data={
                    "url": "https://example.com",
                    "id": "42",
                    "document_state": "URL_ADDED",
                    "document_type": "webpage",
                    "title": "Updated Title",
                    # 'text' is intentionally NOT submitted
                }, headers=API_HEADERS)

        assert resp.status_code == 200
        mock_doc.analyze.assert_called_once()


# ---------------------------------------------------------------------------
# /url_add
# ---------------------------------------------------------------------------


class TestUrlAdd:
    def test_successful_add(self, client):
        mock_session = MagicMock()
        mock_doc = MagicMock()
        mock_doc.id = 100
        with patch("server.get_scoped_session", return_value=mock_session):
            with patch("server.WebDocument", return_value=mock_doc):
                with patch("server.cfg") as mock_cfg:
                    mock_cfg.get.return_value = None  # disable S3 (avoids boto3 import)
                    resp = client.post("/url_add", json={
                        "url": "https://example.com",
                        "type": "link",
                        "title": "Test Link",
                    }, headers=API_HEADERS, content_type="application/json")

        assert resp.status_code == 200
        data = resp.get_json()
        assert data["status"] == "success"
        assert data["document_id"] == 100
        mock_session.add.assert_called_once_with(mock_doc)
        mock_session.commit.assert_called_once()

    def test_missing_required_params(self, client):
        resp = client.post("/url_add", json={"url": "https://example.com"},
                           headers=API_HEADERS, content_type="application/json")
        assert resp.status_code == 400
        data = resp.get_json()
        assert "Missing required" in data["message"]

    def test_add_link_type(self, client):
        """Verify url_add for link type succeeds (no S3 upload for links)."""
        mock_session = MagicMock()
        mock_doc = MagicMock()
        mock_doc.id = 101
        with patch("server.get_scoped_session", return_value=mock_session):
            with patch("server.WebDocument", return_value=mock_doc):
                with patch("server.cfg") as mock_cfg:
                    mock_cfg.get.return_value = None  # disable S3 (avoids boto3 import)
                    resp = client.post("/url_add", json={
                        "url": "https://example.com/article",
                        "type": "link",
                        "title": "An Article",
                        "source": "manual",
                    }, headers=API_HEADERS, content_type="application/json")

        assert resp.status_code == 200
        data = resp.get_json()
        assert data["status"] == "success"
        mock_doc.set_document_type.assert_called_once_with("link")
        mock_doc.set_document_state.assert_called_once_with("URL_ADDED")
        mock_session.add.assert_called_once()
        mock_session.commit.assert_called_once()
