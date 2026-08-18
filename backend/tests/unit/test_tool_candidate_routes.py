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
