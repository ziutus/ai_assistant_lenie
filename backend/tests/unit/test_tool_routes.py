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


def _mutation_session():
    """Session mock whose add() assigns id=42 to the flushed Tool, mimicking a real flush()."""
    from library.db.models import Tool

    session = MagicMock()

    def _assign_id(obj):
        if isinstance(obj, Tool):
            obj.id = 42

    session.add.side_effect = _assign_id
    return session


VALID_BODY = {
    "name": "Terraform",
    "note_path": "Narzedzia/Terraform.md",
    "content": "# Terraform\n\nOpis.",
}


class TestCreateToolServiceKeyForbidden:
    def test_service_key_403_before_any_mutation(self, monkeypatch):
        from library.tool_routes import create_tool

        get_scoped_session_mock = MagicMock()
        monkeypatch.setattr("library.tool_routes.get_scoped_session", get_scoped_session_mock)
        app = Flask(__name__)

        with app.test_request_context("/tools", method="POST", json=VALID_BODY), pytest.raises(Exception) as exc_info:
            g.auth = SimpleNamespace(kind="service", user_id=None)
            create_tool()

        assert exc_info.value.code == 403
        assert get_scoped_session_mock.call_count == 0

    def test_missing_auth_403_before_any_mutation(self, monkeypatch):
        from library.tool_routes import create_tool

        get_scoped_session_mock = MagicMock()
        monkeypatch.setattr("library.tool_routes.get_scoped_session", get_scoped_session_mock)
        app = Flask(__name__)

        with app.test_request_context("/tools", method="POST", json=VALID_BODY), pytest.raises(Exception) as exc_info:
            create_tool()

        assert exc_info.value.code == 403
        assert get_scoped_session_mock.call_count == 0


class TestCreateToolMissingFields:
    @pytest.mark.parametrize("missing_field", ["name", "note_path", "content"])
    def test_missing_required_field_aborts_400(self, monkeypatch, missing_field):
        from library.tool_routes import create_tool

        session = _mutation_session()
        monkeypatch.setattr("library.tool_routes.get_scoped_session", lambda: session)
        body = {k: v for k, v in VALID_BODY.items() if k != missing_field}
        app = Flask(__name__)

        with app.test_request_context("/tools", method="POST", json=body), pytest.raises(Exception) as exc_info:
            g.auth = SimpleNamespace(kind="user", user_id=1)
            create_tool()

        assert exc_info.value.code == 400
        assert session.add.call_count == 0


class TestCreateToolInvalidPath:
    def test_path_escaping_vault_aborts_400_before_mutation(self, monkeypatch):
        from library.tool_routes import VaultPathInvalidError, create_tool

        session = _mutation_session()
        monkeypatch.setattr("library.tool_routes.get_scoped_session", lambda: session)
        monkeypatch.setattr(
            "library.tool_routes.ensure_within_vault",
            MagicMock(side_effect=VaultPathInvalidError("escapes vault")),
        )
        app = Flask(__name__)

        with app.test_request_context("/tools", method="POST", json=VALID_BODY), pytest.raises(Exception) as exc_info:
            g.auth = SimpleNamespace(kind="user", user_id=1)
            create_tool()

        assert exc_info.value.code == 400
        assert session.add.call_count == 0


class TestCreateToolSuccess:
    def test_successful_write_sets_note_path_and_returns_200(self, monkeypatch):
        from library.tool_routes import create_tool

        session = _mutation_session()
        monkeypatch.setattr("library.tool_routes.get_scoped_session", lambda: session)
        monkeypatch.setattr("library.tool_routes.ensure_within_vault", MagicMock(return_value=None))
        write_mock = MagicMock(return_value=SimpleNamespace(id=1))
        monkeypatch.setattr("library.tool_routes.write_note_with_version", write_mock)
        app = Flask(__name__)

        body = dict(VALID_BODY, user_prompt="dodaj notatke o Terraform")
        with app.test_request_context("/tools", method="POST", json=body):
            g.auth = SimpleNamespace(kind="user", user_id=1)
            response = create_tool()

        write_mock.assert_called_once_with(
            session, "Narzedzia/Terraform.md", "# Terraform\n\nOpis.",
            tool_id=42, user_prompt="dodaj notatke o Terraform",
        )
        added_tool = session.add.call_args[0][0]
        assert added_tool.obsidian_note_path == "Narzedzia/Terraform.md"
        assert session.commit.call_count == 1
        assert response.json == {"written": True, "tool_id": 42, "path": "Narzedzia/Terraform.md"}
        assert response.status_code == 200


class TestCreateToolWriteFailure:
    def test_write_failure_returns_502_without_rollback(self, monkeypatch):
        from library.tool_routes import create_tool

        session = _mutation_session()
        monkeypatch.setattr("library.tool_routes.get_scoped_session", lambda: session)
        monkeypatch.setattr("library.tool_routes.ensure_within_vault", MagicMock(return_value=None))
        monkeypatch.setattr(
            "library.tool_routes.write_note_with_version",
            MagicMock(side_effect=OSError("disk full")),
        )
        app = Flask(__name__)

        with app.test_request_context("/tools", method="POST", json=VALID_BODY):
            g.auth = SimpleNamespace(kind="user", user_id=1)
            response = create_tool()

        assert response.json == {"written": False, "error": "obsidian_write_failed", "tool_id": 42}
        assert response.status_code == 502
        assert session.commit.call_count == 0
        assert session.rollback.call_count == 0


class TestCreateToolAcceptedStatus:
    def test_tool_status_set_explicitly_to_accepted(self, monkeypatch):
        from library.tool_routes import create_tool

        session = _mutation_session()
        monkeypatch.setattr("library.tool_routes.get_scoped_session", lambda: session)
        monkeypatch.setattr("library.tool_routes.ensure_within_vault", MagicMock(return_value=None))
        monkeypatch.setattr(
            "library.tool_routes.write_note_with_version", MagicMock(return_value=SimpleNamespace(id=1)),
        )
        app = Flask(__name__)

        with app.test_request_context("/tools", method="POST", json=VALID_BODY):
            g.auth = SimpleNamespace(kind="user", user_id=1)
            create_tool()

        added_tool = session.add.call_args[0][0]
        assert added_tool.status == "accepted"
