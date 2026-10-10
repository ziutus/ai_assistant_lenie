"""Unit tests for the /website_entities endpoints (GET read, POST refresh)."""

from unittest.mock import MagicMock, patch

import pytest

pytest.importorskip("sqlalchemy")
pytest.importorskip("flask")

API_HEADERS = {"x-api-key": "test-api-key"}


@pytest.mark.parametrize("case,expected", [("success", 200), ("missing", 404), ("no_proposal", 409),
                                           ("not_place", 400), ("selected", 200), ("rollback", 500)])
def test_confirm_place(client, case, expected):
    from library.db.models import Document, DocumentEntity, GeocodeCache, EntityReviewDecision
    proposal = GeocodeCache(id=7, query="Huti", resolved=True, lat=49, lon=24, display_name="Huti, Ukraina")
    selected = GeocodeCache(id=8, query="Huty", resolved=True, lat=50, lon=19, display_name="Huty, Polska")
    entity = DocumentEntity(id=1, document_id=10753, entity_type="placeName", entity_text="Huty",
                            variants=["Huty"], source="ner", geocode=proposal, place_verification_status="needs_review")
    doc = Document(id=10753, tags="topic")
    if case == "not_place":
        entity.entity_type = "orgName"
    if case == "no_proposal":
        entity.geocode = None
    session = MagicMock()
    session.get.side_effect = lambda model, key: (
        (None if case == "missing" else entity) if model is DocumentEntity
        else selected if model is GeocodeCache else doc
    )
    if case == "rollback":
        session.commit.side_effect = RuntimeError("test failure")
    with patch("server.get_scoped_session", return_value=session), patch(
        "library.place_verification._get_or_create_geocode"
    ) as lookup:
        response = client.post("/website_entities/1/confirm_place", headers=API_HEADERS,
                               json={"selected_geocode_id": 8} if case == "selected" else {})
    assert response.status_code == expected
    lookup.assert_not_called()
    if expected == 200:
        assert entity.place_verification_status == "confirmed"
        assert entity.source == "manual"
        assert entity.geocode is (selected if case == "selected" else proposal)
        assert "miejsce-" in doc.tags
        audit = next(call.args[0] for call in session.add.call_args_list
                     if isinstance(call.args[0], EntityReviewDecision))
        assert audit.decision == "place_confirmed"
        assert audit.details["geocode_id"] == entity.geocode.id
        assert audit.details["variants"] == ["Huty"]
        session.commit.assert_called_once()
    elif case == "rollback":
        session.rollback.assert_called_once()
    else:
        session.commit.assert_not_called()

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
                MockDoc.get_by_id.return_value = MagicMock(
                    ner_unavailable_at=None, entities_checked_at=None, tags=None,
                )
                with patch("library.entity_service.get_document_entities", return_value=GROUPED):
                    resp = client.get("/website_entities?id=42", headers=API_HEADERS)

        assert resp.status_code == 200
        data = resp.get_json()
        assert data["status"] == "success"
        assert data["id"] == 42
        assert data["entities"] == GROUPED
        assert data["ner_unavailable_at"] is None
        assert data["place_tags"] == []

    def test_returns_only_place_tags_sorted(self, client):
        with patch("server.get_scoped_session", return_value=MagicMock()):
            with patch("server.Document") as MockDoc:
                MockDoc.get_by_id.return_value = MagicMock(
                    ner_unavailable_at=None, entities_checked_at=None,
                    tags="geopolityka,miejsce-rijad, miejsce-aden ,kraj-jemen,miejsce-dammaj",
                )
                with patch("library.entity_service.get_document_entities", return_value=GROUPED):
                    resp = client.get("/website_entities?id=42", headers=API_HEADERS)

        assert resp.get_json()["place_tags"] == ["miejsce-aden", "miejsce-dammaj", "miejsce-rijad"]

    def test_returns_ner_unavailable_timestamp_when_set(self, client):
        import datetime as dt

        with patch("server.get_scoped_session", return_value=MagicMock()):
            with patch("server.Document") as MockDoc:
                MockDoc.get_by_id.return_value = MagicMock(
                    ner_unavailable_at=dt.datetime(2026, 7, 15, 6, 44, 0), entities_checked_at=None,
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

    def test_refresh_queues_enrichment_and_returns_entities(self, client):
        doc = MagicMock(text_md="Article", text=None)
        session = MagicMock()
        with patch("server.get_scoped_session", return_value=session), patch("server.Document") as model, patch(
            "library.entity_service.refresh_document_entities", return_value=[MagicMock()] * 2
        ) as refresh, patch("library.entity_service.get_document_entities", return_value=GROUPED), patch(
            "library.entity_enrichment_service.ensure_entity_enrichment_job", return_value=None
        ) as enqueue, patch("library.place_verification.verify_document_places") as verify:
            model.get_by_id.return_value = doc
            response = client.post("/website_entities", data={"id": "42"}, headers=API_HEADERS)
        assert response.status_code == 202
        assert response.get_json()["refreshed"] == 2
        assert response.get_json()["entities"] == GROUPED
        refresh.assert_called_once_with(session, 42, "Article")
        enqueue.assert_called_once()
        verify.assert_not_called()

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

    def test_refresh_does_not_run_place_verification_inline(self, client):
        doc = MagicMock(text_md="Article", text=None)
        with patch("server.get_scoped_session", return_value=MagicMock()), patch("server.Document") as model, patch(
            "library.entity_service.refresh_document_entities", return_value=[]
        ), patch("library.entity_service.get_document_entities", return_value=GROUPED), patch(
            "library.place_verification.verify_document_places", side_effect=RuntimeError("offline")
        ) as verify:
            model.get_by_id.return_value = doc
            response = client.post("/website_entities", data={"id": "42"}, headers=API_HEADERS)
        assert response.status_code == 202
        assert response.get_json()["enrichment_job"] is None
        verify.assert_not_called()


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


class TestWebsiteEntitiesRename:
    @pytest.mark.parametrize("body", [{}, {"text": "  "}, {"text": None}, {"text": 1},
                                      {"text": "x" * 501}, ["name"]])
    def test_invalid_text(self, client, body):
        assert client.patch("/website_entities/7", json=body, headers=API_HEADERS).status_code == 400

    def test_missing_entity(self, client):
        session = MagicMock()
        session.get.return_value = None
        with patch("server.get_scoped_session", return_value=session):
            assert client.patch("/website_entities/7", json={"text": "Jemen"},
                                headers=API_HEADERS).status_code == 404

    @pytest.mark.parametrize("entity_type", ["persName", "orgName"])
    def test_wrong_type(self, client, entity_type):
        session = MagicMock()
        session.get.return_value = MagicMock(entity_type=entity_type)
        with patch("server.get_scoped_session", return_value=session):
            assert client.patch("/website_entities/7", json={"text": "Jemen"},
                                headers=API_HEADERS).status_code == 400
        session.commit.assert_not_called()

    @pytest.mark.parametrize("entity_type", ["geogName", "placeName"])
    def test_rename_preserves_variants_and_clears_old_verification(self, client, entity_type):
        entity = MagicMock(id=7, document_id=42, entity_type=entity_type,
                           entity_text="Jemenu Północnego", mention_count=3,
                           variants=["Jemenie Północnym", "Jemenu Północnego"], geocode_id=12)
        document = MagicMock()
        session = MagicMock()
        session.get.side_effect = [entity, document]
        session.query.return_value.filter.return_value.first.return_value = None
        item = {"id": 7, "text": "Jemen Północny", "count": 3}
        with patch("server.get_scoped_session", return_value=session), patch(
            "library.entity_service.get_document_entities", return_value={entity_type: [item]}
        ), patch("library.place_verification.remove_orphaned_tag", return_value="miejsce-stare") as remove, patch(
            "library.entity_review_audit.record_entity_decision"
        ) as audit, patch("library.place_verification._get_or_create_geocode", side_effect=TimeoutError):
            resp = client.patch("/website_entities/7", json={"text": "  Jemen Północny  "}, headers=API_HEADERS)
        assert resp.status_code == 200
        assert resp.content_type == "application/json"
        assert resp.get_json()["entity"]["entity_type"] == entity_type
        assert entity.entity_text == "Jemen Północny"
        assert entity.variants == ["Jemenie Północnym", "Jemenu Północnego", "Jemen Północny"]
        assert entity.source == "manual"
        assert entity.mention_count == 3
        assert entity.geocode_id is None and entity.geocode is None
        remove.assert_called_once_with(session, document, entity)
        assert audit.call_args.kwargs["decision"] == "renamed"
        assert audit.call_args.kwargs["entity_text"] == "Jemenu Północnego"
        session.commit.assert_called_once()

    @pytest.mark.parametrize("concurrent", [False, True])
    def test_collision(self, client, concurrent):
        from sqlalchemy.exc import IntegrityError
        session = MagicMock()
        session.get.return_value = MagicMock(id=7, document_id=42, entity_type="geogName",
                                             entity_text="Jemenu", variants=[])
        duplicate = MagicMock(id=8, entity_text="Jemen", entity_type="geogName")
        session.query.return_value.filter.return_value.first.side_effect = [None, duplicate] if concurrent else [duplicate]
        if concurrent:
            session.flush.side_effect = IntegrityError("update", {}, MagicMock(pgcode="23505"))
        with patch("server.get_scoped_session", return_value=session), patch(
            "library.place_verification.remove_orphaned_tag"
        ), patch("library.entity_review_audit.record_entity_decision"):
            resp = client.patch("/website_entities/7", json={"text": "Jemen"}, headers=API_HEADERS)
        assert resp.status_code == 409
        assert "Połącz z innym miejscem" in resp.get_json()["message"]
        assert resp.get_json()["conflict_entity"] == {"id": 8, "text": "Jemen", "entity_type": "geogName"}
        session.commit.assert_not_called()
        if concurrent:
            session.rollback.assert_called_once()

    def test_options(self, client):
        assert client.options("/website_entities/7").status_code == 200

    @pytest.mark.parametrize("failure", [False, True])
    def test_geocodes_renamed_place(self, client, failure):
        entity = MagicMock(id=7, document_id=42, entity_type="geogName",
                           entity_text="Adenu", variants=[], mention_count=1)
        document = MagicMock(tags="topic")
        row = MagicMock(id=12, resolved=True, display_name="Aden, Jemen")
        other = MagicMock(id=8, entity_text="Aden", entity_type="placeName", geocode_id=12, geocode=row)
        session = MagicMock()
        session.get.side_effect = [entity, document]
        session.query.return_value.filter.return_value.first.return_value = None
        session.query.return_value.filter.return_value.all.return_value = [other]
        with patch("server.get_scoped_session", return_value=session), patch(
            "library.place_verification._get_or_create_geocode", return_value=row,
            side_effect=TimeoutError if failure else None,
        ) as lookup, patch("library.place_verification.remove_orphaned_tag"), patch(
            "library.entity_review_audit.record_entity_decision"
        ), patch("library.entity_service.get_document_entities", return_value={
            "geogName": [{"id": 7, "text": "Aden"}],
        }):
            resp = client.patch("/website_entities/7", json={"text": "Aden"}, headers=API_HEADERS)
        assert resp.status_code == 200
        lookup.assert_called_once_with(session, "Aden")
        assert resp.get_json()["geocoded"] is (not failure)
        assert resp.get_json()["same_place_entity"] == (None if failure else {
            "id": 8, "text": "Aden", "entity_type": "placeName",
        })
        assert entity.entity_text == "Aden"
        assert entity.geocode is (None if failure else row)
        assert document.tags == ("topic" if failure else "topic,miejsce-aden")
        session.commit.assert_called_once()


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


class TestPlacesMergeGeocodesTarget:
    """POST /document/<id>/places/merge: a merged target is source='manual' (enrichment skips it)."""

    @staticmethod
    def _entity(entity_id, text, geocode_id=None):
        from library.db.models import DocumentEntity

        return DocumentEntity(
            id=entity_id, document_id=42, entity_type="placeName", entity_text=text,
            mention_count=1, variants=[], source="ner", geocode_id=geocode_id,
        )

    @staticmethod
    def _post(client, source, target, geocode_result=None):
        session = MagicMock()
        session.get.side_effect = lambda model, entity_id: {7: source, 8: target}.get(entity_id)
        geocode = MagicMock(return_value=geocode_result or {"geocoded": True, "same_place_entity": None})
        with patch("server.get_scoped_session", return_value=session), \
                patch("server.Document") as MockDoc, \
                patch("library.entity_review_audit.record_entity_decision") as audit, \
                patch("library.place_verification.geocode_single_place", geocode):
            MockDoc.get_by_id.return_value = MagicMock(id=42)
            resp = client.post(
                "/document/42/places/merge",
                json={"source_entity_id": 7, "target_entity_id": 8},
                headers=API_HEADERS,
            )
        return resp, geocode, audit, session

    def test_geocodes_a_target_neither_side_had_geocoded(self, client):
        source, target = self._entity(7, "Aden"), self._entity(8, "Aden miasto")

        resp, geocode, audit, session = self._post(client, source, target)

        assert resp.status_code == 200
        assert resp.get_json()["geocoded"] is True
        geocode.assert_called_once()
        assert geocode.call_args.args[2] is target
        session.delete.assert_called_once_with(source)
        audit.assert_called_once()

    def test_skips_geocoding_when_target_already_has_it(self, client):
        source, target = self._entity(7, "Aden"), self._entity(8, "Aden miasto", geocode_id=5)

        resp, geocode, _, _ = self._post(client, source, target)

        assert resp.status_code == 200
        assert resp.get_json()["geocoded"] is True
        geocode.assert_not_called()

    def test_unresolved_geocode_still_completes_the_merge(self, client):
        source, target = self._entity(7, "Aden"), self._entity(8, "Aden miasto")

        resp, _, audit, session = self._post(
            client, source, target, geocode_result={"geocoded": False, "same_place_entity": None},
        )

        assert resp.status_code == 200
        assert resp.get_json()["geocoded"] is False
        session.commit.assert_called_once()
        audit.assert_called_once()


class TestInformationSourceUpdate:
    @staticmethod
    def _patch(client, body, source):
        session = MagicMock()
        session.get.return_value = source
        with patch("server.get_scoped_session", return_value=session):
            resp = client.patch("/information_sources/75", json=body, headers=API_HEADERS)
        return resp, session

    def test_unknown_source_returns_404(self, client):
        resp, _ = self._patch(client, {"domain": "telegraph.co.uk"}, None)
        assert resp.status_code == 404

    def test_body_must_be_an_object(self, client):
        from library.db.models import InformationSource

        resp, session = self._patch(client, ["domain"], InformationSource(id=75, canonical_name="The Telegraph"))
        assert resp.status_code == 400
        session.commit.assert_not_called()

    def test_updates_type_domain_and_description(self, client):
        from library.db.models import InformationSource

        source = InformationSource(id=75, canonical_name="The Telegraph")
        resp, session = self._patch(client, {
            "source_type": "newspaper", "domain": "https://www.telegraph.co.uk/", "description": "Dziennik, 1855",
        }, source)

        assert resp.status_code == 200
        data = resp.get_json()
        assert (data["source_type"], data["domain"], data["description"]) == (
            "newspaper", "telegraph.co.uk", "Dziennik, 1855")
        session.commit.assert_called_once()

    def test_bad_domain_returns_400_and_rolls_back(self, client):
        from library.db.models import InformationSource

        resp, session = self._patch(client, {"domain": "nie domena"}, InformationSource(id=75, canonical_name="X"))

        assert resp.status_code == 400
        session.rollback.assert_called_once()
        session.commit.assert_not_called()


class TestOrganizationRenameSyncsSource:
    @staticmethod
    def _patch(client, body, rename_side_effect=None, rename_result=None):
        from library.db.models import Organization

        session = MagicMock()
        session.get.return_value = Organization(id=842, canonical_name="telegrapha")
        session.scalar.return_value = None
        with patch("server.get_scoped_session", return_value=session), \
                patch("library.organization_source_sync.rename_organization",
                      side_effect=rename_side_effect, return_value=rename_result) as rename:
            resp = client.patch("/organizations/842", json=body, headers=API_HEADERS)
        return resp, rename, session

    def test_rename_goes_through_the_syncing_helper_and_reports_the_result(self, client):
        result = {"old_name": "telegrapha", "source": {"action": "merged", "source_id": 75}}

        resp, rename, session = self._patch(client, {"canonical_name": "The Telegraph"}, rename_result=result)

        assert resp.status_code == 200
        assert resp.get_json()["rename"] == result
        assert rename.call_args.args[2] == "The Telegraph"
        session.commit.assert_called_once()

    def test_source_belonging_to_another_organization_returns_409(self, client):
        from library.organization_source_sync import SourceConflictError

        resp, _, session = self._patch(
            client, {"canonical_name": "The Telegraph"}, rename_side_effect=SourceConflictError("zajęte"),
        )

        assert resp.status_code == 409
        assert resp.get_json()["message"] == "zajęte"
        session.rollback.assert_called_once()
        session.commit.assert_not_called()

    def test_description_is_shared_with_the_bound_source(self, client):
        from library.db.models import InformationSource, Organization

        organization = Organization(id=842, canonical_name="The Telegraph")
        source = InformationSource(id=75, canonical_name="The Telegraph", organization_id=842)
        session = MagicMock()
        session.get.return_value = organization
        session.scalar.return_value = source
        with patch("server.get_scoped_session", return_value=session):
            resp = client.patch("/organizations/842", json={"description": "Dziennik"}, headers=API_HEADERS)

        assert resp.status_code == 200
        assert organization.description == source.description == "Dziennik"

    def test_source_conflict_exposes_the_owning_organization_for_a_merge(self, client):
        from library.organization_source_sync import SourceConflictError

        resp, _, _ = self._patch(
            client, {"canonical_name": "The Telegraph"},
            rename_side_effect=SourceConflictError("zajęte", existing_organization_id=281),
        )

        assert resp.status_code == 409
        assert resp.get_json()["existing_organization_id"] == 281


class TestOrganizationMergePreview:
    @staticmethod
    def _get(client, query, *, preview=None, error=None):
        with patch("server.get_scoped_session", return_value=MagicMock()), \
                patch("library.organization_source_sync.merge_preview",
                      side_effect=error, return_value=preview) as mock_preview:
            resp = client.get(f"/organizations/842/merge_preview{query}", headers=API_HEADERS)
        return resp, mock_preview

    def test_target_id_is_required(self, client):
        resp, mock_preview = self._get(client, "")
        assert resp.status_code == 400
        mock_preview.assert_not_called()

    def test_returns_the_comparison(self, client):
        preview = {"source": {"id": 842}, "target": {"id": 281}, "effects": {"source_action": "merge_sources"}}

        resp, mock_preview = self._get(client, "?target_id=281", preview=preview)

        assert resp.status_code == 200
        assert resp.get_json()["effects"] == preview["effects"]
        assert mock_preview.call_args.args[1:] == (842, 281)

    def test_unknown_organization_is_404_and_same_organization_is_400(self, client):
        assert self._get(client, "?target_id=999", error=LookupError("x"))[0].status_code == 404
        assert self._get(client, "?target_id=842", error=ValueError("same"))[0].status_code == 400


class TestOrganizationMergeKeepsSourcesInStep:
    def test_registry_merge_endpoint_goes_through_the_syncing_helper(self, client):
        from library.db.models import Organization

        session = MagicMock()
        session.get.return_value = Organization(id=842, canonical_name="Emiraty")
        result = {"organization_id": 281, "canonical_name": "ZEA", "source": {"action": "merged"}}
        with patch("server.get_scoped_session", return_value=session), \
                patch("library.organization_source_sync.merge_organizations", return_value=result) as merge:
            resp = client.post("/organizations/842/merge", json={"target_organization_id": 281},
                               headers=API_HEADERS)

        assert resp.status_code == 200 and resp.get_json()["source"] == {"action": "merged"}
        assert merge.call_args.args[1:] == (842, 281)
        session.commit.assert_called_once()
