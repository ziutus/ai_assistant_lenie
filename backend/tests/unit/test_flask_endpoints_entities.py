"""Unit tests for the /website_entities endpoints (GET read, POST refresh)."""

from unittest.mock import MagicMock, patch

import pytest

pytest.importorskip("sqlalchemy")
pytest.importorskip("flask")

API_HEADERS = {"x-api-key": "test-api-key"}

GROUPED = {
    "persName": [{"text": "Tusk", "count": 2}],
    "geogName": [{"text": "cieśnina Ormuz", "count": 1}],
    "placeName": [],
}


@pytest.fixture()
def client():
    """Flask test client with auth bypassed (same pattern as test_flask_endpoints_orm)."""
    import server
    server.app.config["TESTING"] = True
    with patch.object(server, "check_auth_header"):
        with server.app.test_client() as c:
            yield c


class TestWebsiteEntitiesGet:
    def test_missing_id_returns_400(self, client):
        resp = client.get("/website_entities", headers=API_HEADERS)
        assert resp.status_code == 400

    @pytest.mark.parametrize("bad_id", ["abc", "0", "-5"])
    def test_invalid_id_returns_400(self, client, bad_id):
        resp = client.get(f"/website_entities?id={bad_id}", headers=API_HEADERS)
        assert resp.status_code == 400

    def test_document_not_found_returns_404(self, client):
        with patch("server.get_scoped_session", return_value=MagicMock()):
            with patch("server.Document") as MockDoc:
                MockDoc.get_by_id.return_value = None
                resp = client.get("/website_entities?id=42", headers=API_HEADERS)
        assert resp.status_code == 404

    def test_returns_grouped_entities(self, client):
        with patch("server.get_scoped_session", return_value=MagicMock()):
            with patch("server.Document") as MockDoc:
                MockDoc.get_by_id.return_value = MagicMock(ner_unavailable_at=None)
                with patch("library.entity_service.get_document_entities", return_value=GROUPED):
                    resp = client.get("/website_entities?id=42", headers=API_HEADERS)

        assert resp.status_code == 200
        data = resp.get_json()
        assert data["status"] == "success"
        assert data["id"] == 42
        assert data["entities"] == GROUPED
        assert data["ner_unavailable_at"] is None

    def test_returns_ner_unavailable_timestamp_when_set(self, client):
        import datetime as dt

        with patch("server.get_scoped_session", return_value=MagicMock()):
            with patch("server.Document") as MockDoc:
                MockDoc.get_by_id.return_value = MagicMock(
                    ner_unavailable_at=dt.datetime(2026, 7, 15, 6, 44, 0),
                )
                with patch("library.entity_service.get_document_entities", return_value=GROUPED):
                    resp = client.get("/website_entities?id=42", headers=API_HEADERS)

        assert resp.get_json()["ner_unavailable_at"] == "2026-07-15T06:44:00"


class TestWebsiteEntitiesRefresh:
    def test_rejects_refresh_when_embeddings_exist(self, client):
        doc = MagicMock(text_md="# Artykuł", text=None)
        with patch("server.get_scoped_session", return_value=MagicMock()), \
                patch("server.Document") as mock_document, \
                patch("library.document_editing.document_has_embeddings", return_value=True):
            mock_document.get_by_id.return_value = doc
            resp = client.post("/website_entities", data={"id": "42"}, headers=API_HEADERS)

        assert resp.status_code == 409

    def test_missing_id_returns_400(self, client):
        resp = client.post("/website_entities", data={}, headers=API_HEADERS)
        assert resp.status_code == 400

    def test_document_without_text_returns_400(self, client):
        doc = MagicMock(text_md=None, text=None)
        with patch("server.get_scoped_session", return_value=MagicMock()):
            with patch("server.Document") as MockDoc:
                MockDoc.get_by_id.return_value = doc
                resp = client.post("/website_entities", data={"id": "42"}, headers=API_HEADERS)
        assert resp.status_code == 400

    def test_refreshes_verifies_and_returns_entities(self, client):
        doc = MagicMock(text_md="# Artykuł o Tusku", text=None)
        session = MagicMock()
        with patch("server.get_scoped_session", return_value=session):
            with patch("server.Document") as MockDoc:
                MockDoc.get_by_id.return_value = doc
                with patch("library.entity_service.refresh_document_entities", return_value=[MagicMock()] * 2) as mock_refresh:
                    with patch("library.place_verification.verify_document_places",
                               return_value={"checked": 1, "resolved": ["Kijów"], "tagged": ["miejsce-kijow"]}) as mock_verify:
                        with patch("library.person_registry.resolve_document_persons",
                                   return_value={"linked": [("Tusk", "Donald Tusk", "wikidata_matched")], "skipped": []}) as mock_persons:
                            with patch("library.overpass_client.attach_document_pipelines",
                                       return_value={"checked": 1, "resolved": ["Baltic Pipe"]}) as mock_pipes:
                                with patch("library.entity_service.get_document_entities", return_value=GROUPED):
                                    resp = client.post("/website_entities", data={"id": "42"}, headers=API_HEADERS)

        assert resp.status_code == 200
        data = resp.get_json()
        assert data["status"] == "success"
        assert data["refreshed"] == 2
        assert data["place_tags"] == ["miejsce-kijow"]
        assert data["persons_linked"] == 1
        assert data["pipelines"] == ["Baltic Pipe"]
        assert data["entities"] == GROUPED
        mock_refresh.assert_called_once_with(session, 42, "# Artykuł o Tusku")
        mock_verify.assert_called_once_with(session, doc, "# Artykuł o Tusku")
        mock_persons.assert_called_once_with(session, doc, "# Artykuł o Tusku")
        mock_pipes.assert_called_once_with(session, 42)
        assert session.commit.call_count == 4  # refresh + miejsca + osoby + rurociągi

    def test_ner_service_unavailable_returns_503(self, client):
        from library.ner_client import NERServiceUnavailable

        doc = MagicMock(text_md="# Artykuł", text=None)
        session = MagicMock()
        with patch("server.get_scoped_session", return_value=session):
            with patch("server.Document") as MockDoc:
                MockDoc.get_by_id.return_value = doc
                with patch("library.entity_service.refresh_document_entities",
                           side_effect=NERServiceUnavailable("boom")):
                    resp = client.post("/website_entities", data={"id": "42"}, headers=API_HEADERS)

        assert resp.status_code == 503
        data = resp.get_json()
        assert data["status"] == "error"
        assert data["ner_unavailable"] is True

    def test_place_verification_failure_does_not_fail_request(self, client):
        doc = MagicMock(text_md="# Artykuł", text=None)
        session = MagicMock()
        with patch("server.get_scoped_session", return_value=session):
            with patch("server.Document") as MockDoc:
                MockDoc.get_by_id.return_value = doc
                with patch("library.entity_service.refresh_document_entities", return_value=[MagicMock()]):
                    with patch("library.place_verification.verify_document_places", side_effect=RuntimeError("boom")):
                        with patch("library.person_registry.resolve_document_persons",
                                   return_value={"linked": [], "skipped": []}):
                            with patch("library.entity_service.get_document_entities", return_value=GROUPED):
                                resp = client.post("/website_entities", data={"id": "42"}, headers=API_HEADERS)

        assert resp.status_code == 200
        assert resp.get_json()["place_tags"] == []
        session.rollback.assert_called_once()


class TestEntityOccurrences:
    """GET /document/<id>/entity_occurrences — rozkład wystąpień encji po rozdziałach."""

    BOOK = ("# Rozdział pierwszy\n\nPutin przemawiał. Krytyka Putina narastała.\n\n"
            "# Rozdział drugi\n\nZupełnie inny temat.\n\n"
            "# Rozdział trzeci\n\nPowrót do Putina.")

    def _client_with(self, doc, entity_rows):
        session = MagicMock()
        session.get.return_value = doc
        session.query.return_value.filter.return_value.all.return_value = entity_rows
        return patch("library.chunk_review_routes.get_scoped_session", return_value=session)

    def test_counts_per_chapter_using_variants(self, client):
        doc = MagicMock(text_md=self.BOOK, text=None)
        row = MagicMock(variants=["Putin", "Putina"])
        with self._client_with(doc, [row]):
            resp = client.get("/document/9/entity_occurrences?text=Putin", headers=API_HEADERS)

        assert resp.status_code == 200
        data = resp.get_json()
        assert data["total"] == 3
        assert data["occurrences"] == [
            {"position": 1, "title": "Rozdział pierwszy", "count": 2},
            {"position": 3, "title": "Rozdział trzeci", "count": 1},
        ]

    def test_missing_entity_falls_back_to_raw_text(self, client):
        doc = MagicMock(text_md=self.BOOK, text=None)
        with self._client_with(doc, []):
            resp = client.get("/document/9/entity_occurrences?text=Putin", headers=API_HEADERS)
        assert resp.get_json()["total"] == 3  # prefiks "Putin" łapie też odmiany

    def test_missing_text_param_returns_400(self, client):
        with self._client_with(MagicMock(), []):
            resp = client.get("/document/9/entity_occurrences", headers=API_HEADERS)
        assert resp.status_code == 400

    def test_no_markdown_chapters_falls_back_to_chunk_chapters(self, client):
        """YouTube transcript: no H1/H2 headers, chapters come from TEMAT chunks."""
        doc = MagicMock(
            text_md=None,
            text="Transkrypcja bez nagłówków markdown. Putin wspomniany. " + "Wypełniacz. " * 10,
        )

        def chunk(id_, position, type_, topic, text):
            c = MagicMock(spec=["id", "position", "type", "topic", "corrected_text", "original_text"])
            c.id, c.position, c.type, c.topic = id_, position, type_, topic
            c.corrected_text, c.original_text = text, None
            return c

        run = MagicMock()
        run.chunks = [
            chunk(201, 1, "TEMAT", "Temat pierwszy", "Rozmowa o Putinie. Sam Putin milczał."),
            chunk(202, 2, "REKLAMA", "Reklama", "Putin w reklamie się nie liczy."),
            chunk(203, 3, "TEMAT", "Temat drugi", "Zupełnie inny temat."),
            chunk(204, 4, "TEMAT", "Temat trzeci", "Krytyka Putina."),
        ]
        with self._client_with(doc, []):
            with patch("library.chunk_review_routes._latest_run_for_document", return_value=run):
                resp = client.get("/document/9/entity_occurrences?text=Putin", headers=API_HEADERS)

        assert resp.status_code == 200
        data = resp.get_json()
        # positions are reader chapter numbers (TEMAT chunks renumbered 1..N)
        assert data["occurrences"] == [
            {"position": 1, "title": "Temat pierwszy", "count": 2},
            {"position": 3, "title": "Temat trzeci", "count": 1},
        ]

    def test_no_chapters_and_no_run_returns_empty_occurrences(self, client):
        doc = MagicMock(text_md=None, text="Tekst bez nagłówków. Putin raz. " + "Wypełniacz. " * 10)
        with self._client_with(doc, []):
            with patch("library.chunk_review_routes._latest_run_for_document", return_value=None):
                resp = client.get("/document/9/entity_occurrences?text=Putin", headers=API_HEADERS)

        data = resp.get_json()
        assert data["occurrences"] == []
        assert data["total"] == 1


class TestWebsiteEntitiesDelete:
    def test_entity_not_found_returns_404(self, client):
        session = MagicMock()
        session.get.return_value = None
        with patch("server.get_scoped_session", return_value=session):
            resp = client.delete("/website_entities/999", headers=API_HEADERS)
        assert resp.status_code == 404

    def test_deletes_place_entity_without_person_link(self, client):
        entity = MagicMock(
            id=7, entity_type="geogName", entity_text="Starling", document_id=42,
            mention_count=2, variants=["Starlinga"],
        )
        session = MagicMock()
        session.get.return_value = entity
        with patch("server.get_scoped_session", return_value=session), patch(
            "library.entity_review_audit.record_entity_decision"
        ) as audit:
            resp = client.delete(
                "/website_entities/7", json={"decision": "excluded_global"}, headers=API_HEADERS
            )

        assert resp.status_code == 200
        data = resp.get_json()
        assert data["deleted_entity_id"] == 7
        assert data["person_link_removed"] is False
        assert audit.call_args.kwargs["decision"] == "excluded_global"
        assert audit.call_args.kwargs["details"] == {
            "mention_count": 2, "variants": ["Starlinga"],
        }
        session.delete.assert_called_once_with(entity)
        session.commit.assert_called_once()

    def test_person_entity_removes_matching_link(self, client):
        entity = MagicMock(
            id=7, entity_type="persName", entity_text="Starling", document_id=42,
            mention_count=1, variants=[],
        )
        link = MagicMock(
            id=11, person_id=5, confidence="wikidata_matched",
            source_excerpt="Starling powiedział...",
        )
        session = MagicMock()
        session.get.return_value = entity
        session.execute.return_value.scalars.return_value.first.return_value = link
        with patch("server.get_scoped_session", return_value=session), patch(
            "library.entity_review_audit.record_entity_decision"
        ) as audit:
            with patch("library.person_registry.reject_review_link",
                       return_value={"action": "reject", "person_deleted": True}) as mock_reject:
                resp = client.delete("/website_entities/7", headers=API_HEADERS)

        assert resp.status_code == 200
        data = resp.get_json()
        assert data["person_link_removed"] is True
        assert data["person_deleted"] is True
        mock_reject.assert_called_once_with(session, link)
        assert audit.call_args.kwargs["document_person_id"] == 11
        assert audit.call_args.kwargs["original_confidence"] == "wikidata_matched"
        session.delete.assert_called_once_with(entity)

    def test_invalid_audit_decision_returns_400(self, client):
        resp = client.delete(
            "/website_entities/7", json={"decision": "unknown"}, headers=API_HEADERS
        )
        assert resp.status_code == 400

    def test_other_reason_requires_comment(self, client):
        resp = client.delete(
            "/website_entities/7",
            json={"decision": "rejected", "reason_code": "other"},
            headers=API_HEADERS,
        )
        assert resp.status_code == 400

    def test_reject_stores_reason_and_comment(self, client):
        entity = MagicMock(
            id=7, entity_type="geogName", entity_text="Starling", document_id=42,
            mention_count=1, variants=[],
        )
        session = MagicMock()
        session.get.return_value = entity
        with patch("server.get_scoped_session", return_value=session), patch(
            "library.entity_review_audit.record_entity_decision"
        ) as audit:
            resp = client.delete(
                "/website_entities/7",
                json={
                    "decision": "rejected",
                    "reason_code": "misread_name",
                    "comment": "Artefakt transkrypcji",
                },
                headers=API_HEADERS,
            )

        assert resp.status_code == 200
        assert audit.call_args.kwargs["reason_code"] == "misread_name"
        assert audit.call_args.kwargs["comment"] == "Artefakt transkrypcji"


class TestDocumentPersonsDecide:
    def test_link_not_found_returns_404(self, client):
        session = MagicMock()
        session.get.return_value = None
        with patch("server.get_scoped_session", return_value=session):
            resp = client.patch("/document_persons/999", json={"action": "reject"}, headers=API_HEADERS)
        assert resp.status_code == 404

    def test_invalid_action_returns_400(self, client):
        resp = client.patch("/document_persons/1", json={"action": "frobnicate"}, headers=API_HEADERS)
        assert resp.status_code == 400

    def test_reject_works_for_confident_link(self, client):
        """Editor path: no 409 gate — a wrong wikidata_matched link can be undone."""
        link = MagicMock(
            id=1, document_id=42, person_id=5, raw_mention="Starling",
            confidence="wikidata_matched", source_excerpt="Starling powiedział...",
            role="mentioned",
        )
        session = MagicMock()
        session.get.return_value = link
        with patch("server.get_scoped_session", return_value=session), patch(
            "library.entity_review_audit.record_entity_decision"
        ) as audit:
            with patch("library.person_registry.reject_review_link",
                       return_value={"action": "reject", "link_id": 1, "person_id": 5,
                                     "person_deleted": False}) as mock_reject:
                resp = client.patch("/document_persons/1", json={"action": "reject"}, headers=API_HEADERS)

        assert resp.status_code == 200
        assert resp.get_json()["action"] == "reject"
        mock_reject.assert_called_once_with(session, link)
        assert audit.call_args.kwargs["decision"] == "rejected"
        assert audit.call_args.kwargs["entity_text"] == "Starling"
        session.commit.assert_called_once()

    def test_review_queue_endpoint_still_gates_on_manual_review(self, client):
        link = MagicMock(confidence="wikidata_matched")
        session = MagicMock()
        session.get.return_value = link
        with patch("server.get_scoped_session", return_value=session):
            resp = client.patch("/persons_review/1", json={"action": "reject"}, headers=API_HEADERS)
        assert resp.status_code == 409


class TestPersonAliasAdd:
    def test_missing_alias_returns_400(self, client):
        resp = client.post("/persons/1/aliases", json={}, headers=API_HEADERS)
        assert resp.status_code == 400

    def test_person_not_found_returns_404(self, client):
        session = MagicMock()
        session.get.return_value = None
        with patch("server.get_scoped_session", return_value=session):
            resp = client.post("/persons/999/aliases", json={"alias": "Starlinek"}, headers=API_HEADERS)
        assert resp.status_code == 404

    def test_adds_alias(self, client):
        person = MagicMock()
        person.aliases = [MagicMock(alias="Starlinek")]
        session = MagicMock()
        session.get.return_value = person
        with patch("server.get_scoped_session", return_value=session):
            with patch("library.person_registry.add_person_alias", return_value=True) as mock_add:
                resp = client.post("/persons/5/aliases", json={"alias": "Starlinek"}, headers=API_HEADERS)

        assert resp.status_code == 200
        data = resp.get_json()
        assert data["added"] is True
        assert data["aliases"] == ["Starlinek"]
        mock_add.assert_called_once_with(session, person, "Starlinek")
        session.commit.assert_called_once()
