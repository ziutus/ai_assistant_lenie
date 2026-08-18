import datetime as dt
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

pytest.importorskip("sqlalchemy")

from flask import Flask, g


def _compiled(query) -> str:
    return str(query.compile(compile_kwargs={"literal_binds": True}))


def _session_with_rows(rows):
    session = MagicMock()
    session.execute.return_value.all.return_value = rows
    return session


def _session_for_mutation(candidate, document, similar_tool_name=None):
    session = MagicMock()
    lookup_result = MagicMock()
    lookup_result.first.return_value = (candidate, document)
    duplicate_result = MagicMock()
    duplicate_result.scalars.return_value.first.return_value = (
        SimpleNamespace(name=similar_tool_name) if similar_tool_name else None
    )
    session.execute.side_effect = [lookup_result, duplicate_result]
    return session


def _session_for_lookup_only(candidate, document):
    session = MagicMock()
    lookup_result = MagicMock()
    lookup_result.first.return_value = (candidate, document)
    session.execute.side_effect = [lookup_result]
    return session


def _make_candidate(status="pending"):
    return SimpleNamespace(
        id=1, name="Terraform", status=status, context_snippet="Uzywamy Terraform do IaC",
        detected_by="bielik", created_at=dt.datetime(2026, 8, 10, 12, 0, tzinfo=dt.timezone.utc),
        reviewed_at=None, source_document_id=9381,
    )


def _make_document():
    return SimpleNamespace(
        id=9381, title="Artykul o Terraform", url="https://example.com/terraform", byline="Jan Kowalski",
        discovery_source=SimpleNamespace(name="unknow.news"),
        published_on=dt.date(2026, 8, 1), ingested_at=dt.datetime(2026, 8, 2, 8, 0, tzinfo=dt.timezone.utc),
    )


class TestDefaultStatus:
    def test_missing_status_param_filters_pending(self, monkeypatch):
        from library.tool_candidate_routes import get_tool_candidates

        session = _session_with_rows([])
        monkeypatch.setattr("library.tool_candidate_routes.get_scoped_session", lambda: session)
        app = Flask(__name__)

        with app.test_request_context("/tool_candidates"):
            g.auth = SimpleNamespace(kind="service", user_id=None)
            response = get_tool_candidates()

        assert response.json["filters"] == {"status": "pending", "source": None}
        compiled_query = _compiled(session.execute.call_args[0][0])
        assert "'pending'" in compiled_query


class TestExplicitStatus:
    def test_explicit_status_filters_accepted(self, monkeypatch):
        from library.tool_candidate_routes import get_tool_candidates

        session = _session_with_rows([])
        monkeypatch.setattr("library.tool_candidate_routes.get_scoped_session", lambda: session)
        app = Flask(__name__)

        with app.test_request_context("/tool_candidates?status=accepted"):
            g.auth = SimpleNamespace(kind="service", user_id=None)
            response = get_tool_candidates()

        assert response.json["filters"] == {"status": "accepted", "source": None}
        compiled_query = _compiled(session.execute.call_args[0][0])
        assert "'accepted'" in compiled_query

    def test_unknown_status_aborts_400(self, monkeypatch):
        from library.tool_candidate_routes import get_tool_candidates

        session = _session_with_rows([])
        monkeypatch.setattr("library.tool_candidate_routes.get_scoped_session", lambda: session)
        app = Flask(__name__)

        with app.test_request_context("/tool_candidates?status=nieznany"), pytest.raises(Exception) as exc_info:
            g.auth = SimpleNamespace(kind="service", user_id=None)
            get_tool_candidates()

        assert exc_info.value.code == 400


class TestSourceFilter:
    def test_source_filter_uses_unaccent_lower_subquery(self, monkeypatch):
        from library.tool_candidate_routes import get_tool_candidates

        session = _session_with_rows([])
        monkeypatch.setattr("library.tool_candidate_routes.get_scoped_session", lambda: session)
        app = Flask(__name__)

        with app.test_request_context("/tool_candidates?source=unknow.news"):
            g.auth = SimpleNamespace(kind="service", user_id=None)
            response = get_tool_candidates()

        assert response.json["filters"] == {"status": "pending", "source": "unknow.news"}
        compiled_query = _compiled(session.execute.call_args[0][0])
        assert "unaccent(lower(discovery_sources.name))" in compiled_query
        assert "'unknow.news'" in compiled_query

    def test_missing_source_has_no_discovery_source_where(self, monkeypatch):
        from library.tool_candidate_routes import get_tool_candidates

        session = _session_with_rows([])
        monkeypatch.setattr("library.tool_candidate_routes.get_scoped_session", lambda: session)
        app = Flask(__name__)

        with app.test_request_context("/tool_candidates"):
            g.auth = SimpleNamespace(kind="service", user_id=None)
            get_tool_candidates()

        compiled_query = _compiled(session.execute.call_args[0][0])
        assert "discovery_source_id IN" not in compiled_query


class TestAuthBothKinds:
    @pytest.mark.parametrize("auth", [
        SimpleNamespace(kind="service", user_id=None),
        SimpleNamespace(kind="user", user_id=1),
    ])
    def test_both_kinds_get_200(self, monkeypatch, auth):
        from library.tool_candidate_routes import get_tool_candidates

        session = _session_with_rows([])
        monkeypatch.setattr("library.tool_candidate_routes.get_scoped_session", lambda: session)
        app = Flask(__name__)

        with app.test_request_context("/tool_candidates"):
            g.auth = auth
            response = get_tool_candidates()

        assert response.json["tool_candidates"] == []


class TestAuthMissing:
    def test_missing_auth_aborts_403(self, monkeypatch):
        from library.tool_candidate_routes import get_tool_candidates

        session = _session_with_rows([])
        monkeypatch.setattr("library.tool_candidate_routes.get_scoped_session", lambda: session)
        app = Flask(__name__)

        with app.test_request_context("/tool_candidates"), pytest.raises(Exception) as exc_info:
            get_tool_candidates()

        assert exc_info.value.code == 403


class TestProvenance:
    def test_response_shape_includes_provenance_and_snippet(self, monkeypatch):
        from library.tool_candidate_routes import get_tool_candidates

        candidate = SimpleNamespace(
            id=1, name="Terraform", status="pending", context_snippet="Uzywamy Terraform do IaC",
            detected_by="bielik", created_at=dt.datetime(2026, 8, 10, 12, 0, tzinfo=dt.timezone.utc),
            reviewed_at=None, source_document_id=9381,
        )
        document = SimpleNamespace(
            id=9381, title="Artykul o Terraform", url="https://example.com/terraform", byline="Jan Kowalski",
            discovery_source=SimpleNamespace(name="unknow.news"),
            published_on=dt.date(2026, 8, 1), ingested_at=dt.datetime(2026, 8, 2, 8, 0, tzinfo=dt.timezone.utc),
        )
        session = _session_with_rows([(candidate, document)])
        monkeypatch.setattr("library.tool_candidate_routes.get_scoped_session", lambda: session)
        app = Flask(__name__)

        with app.test_request_context("/tool_candidates"):
            g.auth = SimpleNamespace(kind="user", user_id=1)
            response = get_tool_candidates()

        assert response.json["tool_candidates"] == [{
            "id": 1,
            "name": "Terraform",
            "status": "pending",
            "context_snippet": "Uzywamy Terraform do IaC",
            "detected_by": "bielik",
            "created_at": "2026-08-10T12:00:00+00:00",
            "reviewed_at": None,
            "source_document_id": 9381,
            "source_document": {
                "id": 9381,
                "title": "Artykul o Terraform",
                "url": "https://example.com/terraform",
                "byline": "Jan Kowalski",
                "discovery_source": "unknow.news",
                "published_on": "2026-08-01",
                "ingested_at": "2026-08-02T08:00:00+00:00",
            },
        }]


class TestProvenanceMissingDiscoverySource:
    def test_document_without_discovery_source_returns_none(self, monkeypatch):
        from library.tool_candidate_routes import get_tool_candidates

        candidate = SimpleNamespace(
            id=2, name="Kubernetes", status="pending", context_snippet="Wdrazamy na Kubernetes",
            detected_by="bielik", created_at=dt.datetime(2026, 8, 11, 9, 0, tzinfo=dt.timezone.utc),
            reviewed_at=None, source_document_id=8760,
        )
        document = SimpleNamespace(
            id=8760, title="Artykul o Kubernetes", url="https://example.com/k8s", byline=None,
            discovery_source=None, published_on=None, ingested_at=None,
        )
        session = _session_with_rows([(candidate, document)])
        monkeypatch.setattr("library.tool_candidate_routes.get_scoped_session", lambda: session)
        app = Flask(__name__)

        with app.test_request_context("/tool_candidates"):
            g.auth = SimpleNamespace(kind="service", user_id=None)
            response = get_tool_candidates()

        assert response.json["tool_candidates"][0]["source_document"]["discovery_source"] is None


class TestAcceptEndpoint:
    def test_accept_without_duplicate(self, monkeypatch):
        from library.tool_candidate_routes import accept_candidate

        candidate = _make_candidate()
        document = _make_document()
        session = _session_for_mutation(candidate, document)
        monkeypatch.setattr("library.tool_candidate_routes.get_scoped_session", lambda: session)
        app = Flask(__name__)

        with app.test_request_context("/tool_candidates/1/accept", method="POST"):
            g.auth = SimpleNamespace(kind="user", user_id=1)
            response = accept_candidate(1)

        assert candidate.status == "accepted"
        assert candidate.reviewed_at is not None
        assert response.json["warning"] is None
        assert session.commit.call_count == 1

    def test_accept_with_duplicate_warns_but_still_accepts(self, monkeypatch):
        from library.tool_candidate_routes import accept_candidate

        candidate = _make_candidate()
        document = _make_document()
        session = _session_for_mutation(candidate, document, similar_tool_name="Terraform")
        monkeypatch.setattr("library.tool_candidate_routes.get_scoped_session", lambda: session)
        app = Flask(__name__)

        with app.test_request_context("/tool_candidates/1/accept", method="POST"):
            g.auth = SimpleNamespace(kind="user", user_id=1)
            response = accept_candidate(1)

        assert candidate.status == "accepted"
        assert "Terraform" in response.json["warning"]

    def test_service_key_forbidden(self, monkeypatch):
        from library.tool_candidate_routes import accept_candidate

        candidate = _make_candidate()
        document = _make_document()
        session = _session_for_mutation(candidate, document)
        monkeypatch.setattr("library.tool_candidate_routes.get_scoped_session", lambda: session)
        app = Flask(__name__)

        with app.test_request_context("/tool_candidates/1/accept", method="POST"), pytest.raises(Exception) as exc_info:
            g.auth = SimpleNamespace(kind="service", user_id=None)
            accept_candidate(1)

        assert exc_info.value.code == 403

    def test_unknown_id_aborts_404(self, monkeypatch):
        from library.tool_candidate_routes import accept_candidate

        session = MagicMock()
        session.execute.return_value.first.return_value = None
        monkeypatch.setattr("library.tool_candidate_routes.get_scoped_session", lambda: session)
        app = Flask(__name__)

        with app.test_request_context("/tool_candidates/999/accept", method="POST"), pytest.raises(Exception) as exc_info:
            g.auth = SimpleNamespace(kind="user", user_id=1)
            accept_candidate(999)

        assert exc_info.value.code == 404


class TestRejectEndpoint:
    def test_reject_sets_status_zero_cost(self, monkeypatch):
        from library.tool_candidate_routes import reject_candidate

        candidate = _make_candidate()
        document = _make_document()
        session = _session_for_lookup_only(candidate, document)
        monkeypatch.setattr("library.tool_candidate_routes.get_scoped_session", lambda: session)
        app = Flask(__name__)

        with app.test_request_context("/tool_candidates/1/reject", method="POST"):
            g.auth = SimpleNamespace(kind="user", user_id=1)
            reject_candidate(1)

        assert candidate.status == "rejected"
        assert candidate.reviewed_at is not None
        assert session.execute.call_count == 1

    def test_service_key_forbidden(self, monkeypatch):
        from library.tool_candidate_routes import reject_candidate

        candidate = _make_candidate()
        document = _make_document()
        session = _session_for_lookup_only(candidate, document)
        monkeypatch.setattr("library.tool_candidate_routes.get_scoped_session", lambda: session)
        app = Flask(__name__)

        with app.test_request_context("/tool_candidates/1/reject", method="POST"), pytest.raises(Exception) as exc_info:
            g.auth = SimpleNamespace(kind="service", user_id=None)
            reject_candidate(1)

        assert exc_info.value.code == 403


class TestDeferEndpoint:
    def test_defer_sets_status(self, monkeypatch):
        from library.tool_candidate_routes import defer_candidate

        candidate = _make_candidate()
        document = _make_document()
        session = _session_for_lookup_only(candidate, document)
        monkeypatch.setattr("library.tool_candidate_routes.get_scoped_session", lambda: session)
        app = Flask(__name__)

        with app.test_request_context("/tool_candidates/1/defer", method="POST"):
            g.auth = SimpleNamespace(kind="user", user_id=1)
            defer_candidate(1)

        assert candidate.status == "deferred"

    def test_service_key_forbidden(self, monkeypatch):
        from library.tool_candidate_routes import defer_candidate

        candidate = _make_candidate()
        document = _make_document()
        session = _session_for_lookup_only(candidate, document)
        monkeypatch.setattr("library.tool_candidate_routes.get_scoped_session", lambda: session)
        app = Flask(__name__)

        with app.test_request_context("/tool_candidates/1/defer", method="POST"), pytest.raises(Exception) as exc_info:
            g.auth = SimpleNamespace(kind="service", user_id=None)
            defer_candidate(1)

        assert exc_info.value.code == 403


class TestFindSimilarToolName:
    def test_returns_name_when_similar_tool_exists(self):
        from library.tool_candidate_routes import _find_similar_tool_name

        session = MagicMock()
        session.execute.return_value.scalars.return_value.first.return_value = SimpleNamespace(name="Terraform")

        result = _find_similar_tool_name(session, "terraform")

        assert result == "Terraform"

    def test_returns_none_when_no_similar_tool(self):
        from library.tool_candidate_routes import _find_similar_tool_name

        session = MagicMock()
        session.execute.return_value.scalars.return_value.first.return_value = None

        result = _find_similar_tool_name(session, "terraform")

        assert result is None

    def test_threshold_compiled_into_sql(self):
        from library.tool_candidate_routes import _find_similar_tool_name

        session = MagicMock()
        session.execute.return_value.scalars.return_value.first.return_value = None

        _find_similar_tool_name(session, "terraform")

        compiled_query = _compiled(session.execute.call_args[0][0])
        assert "0.5" in compiled_query
