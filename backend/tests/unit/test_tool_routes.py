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
    session.execute.return_value.scalars.return_value.all.return_value = rows
    return session


def _make_tool(**overrides):
    defaults = dict(
        id=1, uuid="11111111-1111-1111-1111-111111111111", name="Terraform",
        category_tags=["infrastructure-as-code"], homepage_url="https://terraform.io",
        license="MPL-2.0", pricing="free", personal_notes="uzywamy w projekcie X",
        source_document_id=9381, source_candidate_id=5, status="accepted",
        obsidian_note_path="Narzedzia/Terraform.md",
        created_at=dt.datetime(2026, 8, 10, 12, 0, tzinfo=dt.timezone.utc),
        updated_at=dt.datetime(2026, 8, 11, 9, 0, tzinfo=dt.timezone.utc),
    )
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


class TestNoTagFilter:
    def test_missing_tag_param_lists_everything(self, monkeypatch):
        from library.tool_routes import get_tools

        session = _session_with_rows([])
        monkeypatch.setattr("library.tool_routes.get_scoped_session", lambda: session)
        app = Flask(__name__)

        with app.test_request_context("/tools"):
            g.auth = SimpleNamespace(kind="service", user_id=None)
            response = get_tools()

        assert response.json["filters"] == {"tag": None}
        compiled_query = str(session.execute.call_args[0][0].compile())
        assert "@>" not in compiled_query


class TestTagFilter:
    def test_tag_param_filters_with_jsonb_containment(self, monkeypatch):
        from library.tool_routes import get_tools

        session = _session_with_rows([])
        monkeypatch.setattr("library.tool_routes.get_scoped_session", lambda: session)
        app = Flask(__name__)

        with app.test_request_context("/tools?tag=infrastructure-as-code"):
            g.auth = SimpleNamespace(kind="service", user_id=None)
            response = get_tools()

        assert response.json["filters"] == {"tag": "infrastructure-as-code"}
        compiled = session.execute.call_args[0][0].compile()
        assert "@>" in str(compiled)
        assert compiled.params["category_tags_1"] == ["infrastructure-as-code"]


class TestEmptyResult:
    def test_empty_table_returns_empty_list_status_200(self, monkeypatch):
        from library.tool_routes import get_tools

        session = _session_with_rows([])
        monkeypatch.setattr("library.tool_routes.get_scoped_session", lambda: session)
        app = Flask(__name__)

        with app.test_request_context("/tools"):
            g.auth = SimpleNamespace(kind="user", user_id=1)
            response = get_tools()

        assert response.json["tools"] == []
        assert response.status_code == 200


class TestResponseShape:
    def test_response_shape_matches_tool_dict(self, monkeypatch):
        from library.tool_routes import get_tools

        tool = _make_tool()
        session = _session_with_rows([tool])
        monkeypatch.setattr("library.tool_routes.get_scoped_session", lambda: session)
        app = Flask(__name__)

        with app.test_request_context("/tools"):
            g.auth = SimpleNamespace(kind="user", user_id=1)
            response = get_tools()

        assert response.json["tools"] == [{
            "id": 1,
            "uuid": "11111111-1111-1111-1111-111111111111",
            "name": "Terraform",
            "category_tags": ["infrastructure-as-code"],
            "homepage_url": "https://terraform.io",
            "license": "MPL-2.0",
            "pricing": "free",
            "personal_notes": "uzywamy w projekcie X",
            "source_document_id": 9381,
            "source_candidate_id": 5,
            "status": "accepted",
            "obsidian_note_path": "Narzedzia/Terraform.md",
            "created_at": "2026-08-10T12:00:00+00:00",
            "updated_at": "2026-08-11T09:00:00+00:00",
        }]

    def test_null_dates_pass_through_as_none(self, monkeypatch):
        from library.tool_routes import get_tools

        tool = _make_tool(created_at=None, updated_at=None)
        session = _session_with_rows([tool])
        monkeypatch.setattr("library.tool_routes.get_scoped_session", lambda: session)
        app = Flask(__name__)

        with app.test_request_context("/tools"):
            g.auth = SimpleNamespace(kind="user", user_id=1)
            response = get_tools()

        assert response.json["tools"][0]["created_at"] is None
        assert response.json["tools"][0]["updated_at"] is None


class TestAuthBothKinds:
    @pytest.mark.parametrize("auth", [
        SimpleNamespace(kind="service", user_id=None),
        SimpleNamespace(kind="user", user_id=1),
    ])
    def test_both_kinds_get_200(self, monkeypatch, auth):
        from library.tool_routes import get_tools

        session = _session_with_rows([])
        monkeypatch.setattr("library.tool_routes.get_scoped_session", lambda: session)
        app = Flask(__name__)

        with app.test_request_context("/tools"):
            g.auth = auth
            response = get_tools()

        assert response.json["tools"] == []


class TestAuthMissing:
    def test_missing_auth_aborts_403(self, monkeypatch):
        from library.tool_routes import get_tools

        session = _session_with_rows([])
        monkeypatch.setattr("library.tool_routes.get_scoped_session", lambda: session)
        app = Flask(__name__)

        with app.test_request_context("/tools"), pytest.raises(Exception) as exc_info:
            get_tools()

        assert exc_info.value.code == 403


class TestOrdering:
    def test_query_orders_by_name(self, monkeypatch):
        from library.tool_routes import get_tools

        session = _session_with_rows([])
        monkeypatch.setattr("library.tool_routes.get_scoped_session", lambda: session)
        app = Flask(__name__)

        with app.test_request_context("/tools"):
            g.auth = SimpleNamespace(kind="service", user_id=None)
            get_tools()

        compiled_query = _compiled(session.execute.call_args[0][0])
        assert "ORDER BY tools.name" in compiled_query
