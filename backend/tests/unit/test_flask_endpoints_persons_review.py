"""Unit tests for the /persons_review endpoints (manual_review queue + decisions)."""

from unittest.mock import MagicMock, patch

import pytest

pytest.importorskip("sqlalchemy")
pytest.importorskip("flask")

API_HEADERS = {"x-api-key": "test-api-key"}

QUEUE = [
    {
        "link_id": 100, "document_id": 9216, "document_title": "Wywiad", "document_type": "youtube",
        "person_id": 7, "canonical_name": "Jimmy Rushton", "description": None,
        "wikidata_qid": None, "aliases": [], "raw_mention": "Jimmy Ruston",
        "created_at": "2026-07-10T10:00:00",
    },
]


@pytest.fixture()
def client():
    """Flask test client with auth bypassed (same pattern as test_flask_endpoints_entities)."""
    import server
    server.app.config["TESTING"] = True
    with patch.object(server, "check_auth_header"):
        with server.app.test_client() as c:
            yield c


def _review_link(confidence="manual_review", person_id=7):
    link = MagicMock()
    link.id = 100
    link.person_id = person_id
    link.confidence = confidence
    return link


class TestPersonsReviewList:
    def test_returns_queue_entries(self, client):
        with patch("server.get_scoped_session", return_value=MagicMock()):
            with patch("library.person_registry.list_manual_review", return_value=QUEUE):
                resp = client.get("/persons_review", headers=API_HEADERS)

        assert resp.status_code == 200
        data = resp.get_json()
        assert data["status"] == "success"
        assert data["count"] == 1
        assert data["entries"] == QUEUE


class TestPersonsReviewDecide:
    @pytest.mark.parametrize("body", [{}, {"action": "delete"}, {"action": ""}])
    def test_invalid_action_returns_400(self, client, body):
        resp = client.patch("/persons_review/100", json=body, headers=API_HEADERS)
        assert resp.status_code == 400

    def test_link_not_found_returns_404(self, client):
        session = MagicMock()
        session.get.return_value = None
        with patch("server.get_scoped_session", return_value=session):
            resp = client.patch("/persons_review/100", json={"action": "approve"}, headers=API_HEADERS)
        assert resp.status_code == 404

    def test_already_decided_entry_returns_409(self, client):
        session = MagicMock()
        session.get.return_value = _review_link(confidence="manual_confirmed")
        with patch("server.get_scoped_session", return_value=session):
            resp = client.patch("/persons_review/100", json={"action": "approve"}, headers=API_HEADERS)
        assert resp.status_code == 409

    def test_approve_commits_and_returns_result(self, client):
        session = MagicMock()
        session.get.return_value = _review_link()
        with patch("server.get_scoped_session", return_value=session):
            with patch("library.person_registry.approve_review_link",
                       return_value={"action": "approve", "link_id": 100, "person_id": 7}) as mock_approve:
                resp = client.patch("/persons_review/100", json={"action": "approve"}, headers=API_HEADERS)

        assert resp.status_code == 200
        data = resp.get_json()
        assert data["status"] == "success"
        assert data["action"] == "approve"
        mock_approve.assert_called_once()
        session.commit.assert_called_once()

    def test_reject_commits_and_returns_result(self, client):
        session = MagicMock()
        session.get.return_value = _review_link()
        with patch("server.get_scoped_session", return_value=session):
            with patch("library.person_registry.reject_review_link",
                       return_value={"action": "reject", "link_id": 100, "person_id": 7,
                                     "person_deleted": True}):
                resp = client.patch("/persons_review/100", json={"action": "reject"}, headers=API_HEADERS)

        assert resp.status_code == 200
        assert resp.get_json()["person_deleted"] is True
        session.commit.assert_called_once()

    @pytest.mark.parametrize("target", [None, "abc", 0, -3])
    def test_merge_requires_valid_target(self, client, target):
        session = MagicMock()
        session.get.return_value = _review_link()
        with patch("server.get_scoped_session", return_value=session):
            resp = client.patch("/persons_review/100",
                                json={"action": "merge", "target_person_id": target},
                                headers=API_HEADERS)
        assert resp.status_code == 400
        session.commit.assert_not_called()

    def test_merge_target_not_found_returns_404(self, client):
        link = _review_link()
        session = MagicMock()
        session.get.side_effect = [link, None]  # link found, target person not
        with patch("server.get_scoped_session", return_value=session):
            resp = client.patch("/persons_review/100",
                                json={"action": "merge", "target_person_id": 9},
                                headers=API_HEADERS)
        assert resp.status_code == 404

    def test_merge_commits_and_returns_result(self, client):
        link = _review_link()
        target = MagicMock()
        target.id = 9
        session = MagicMock()
        session.get.side_effect = [link, target]
        with patch("server.get_scoped_session", return_value=session):
            with patch("library.person_registry.merge_review_link",
                       return_value={"action": "merge", "link_id": 100, "person_id": 9,
                                     "source_person_id": 7, "person_deleted": True,
                                     "link_dropped_as_duplicate": False}) as mock_merge:
                resp = client.patch("/persons_review/100",
                                    json={"action": "merge", "target_person_id": 9},
                                    headers=API_HEADERS)

        assert resp.status_code == 200
        data = resp.get_json()
        assert data["person_id"] == 9
        assert data["source_person_id"] == 7
        mock_merge.assert_called_once_with(session, link, target)
        session.commit.assert_called_once()

    def test_value_error_rolls_back_returns_400(self, client):
        link = _review_link(person_id=9)
        target = MagicMock()
        target.id = 9
        session = MagicMock()
        session.get.side_effect = [link, target]
        with patch("server.get_scoped_session", return_value=session):
            with patch("library.person_registry.merge_review_link",
                       side_effect=ValueError("target_person_id points at the same person")):
                resp = client.patch("/persons_review/100",
                                    json={"action": "merge", "target_person_id": 9},
                                    headers=API_HEADERS)

        assert resp.status_code == 400
        session.rollback.assert_called_once()
        session.commit.assert_not_called()
