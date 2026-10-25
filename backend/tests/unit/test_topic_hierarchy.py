import json
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from flask import Flask, g
from sqlalchemy.dialects import postgresql

from library import content_group_service as groups
from library import content_group_suggestion_service as suggestions
from library import prompt_templates
from library import feed_routes
from library.db.models import ContentGroup, ContentGroupSuggestion, ContentGroupSuggestionRun, Document, FeedItem, Job


CATALOG = [
    {"id": 1, "name": "Informatyka"},
    {"id": 2, "name": "Web development", "parent_id": 1},
    {"id": 3, "name": "React", "parent_id": 2},
    {"id": 4, "name": "Zoologia"},
]


def session_with_topics():
    session = MagicMock()
    session.scalars.return_value.all.return_value = [ContentGroup(**item, kind="topic") for item in CATALOG]
    return session


@pytest.mark.parametrize("group_id,parent_id,kind,message", [
    (1, 1, "topic", "a topic cannot be its own ancestor"),
    (1, 3, "topic", "a topic cannot be its own ancestor"),
    (4, 3, "topic", "topic hierarchy is limited to 3 levels"),
    (1, 4, "topic", "topic hierarchy is limited to 3 levels"),
    (4, 1, "priority", "only topics can have a parent"),
    (4, 99, "topic", "parent must be an active topic"),
    (4, True, "topic", "parent_id must be an integer"),
    (4, "1", "topic", "parent_id must be an integer"),
])
def test_invalid_parent(group_id, parent_id, kind, message):
    with pytest.raises(ValueError, match=message):
        groups.validate_parent(session_with_topics(), ContentGroup(id=group_id), parent_id, kind)


def test_archived_parent_is_excluded_by_query():
    session = session_with_topics()
    session.scalars.return_value.all.return_value = []
    with pytest.raises(ValueError, match="parent must be an active topic"):
        groups.validate_parent(session, None, 1, "topic")
    query = str(session.scalars.call_args.args[0])
    assert "content_groups.archived_at IS NULL" in query
    assert "content_groups.kind =" in query


def test_none_clears_and_valid_parent_uses_one_query():
    session = session_with_topics()
    assert groups.validate_parent(session, ContentGroup(id=2), None, "topic") is None
    session.scalars.assert_not_called()
    assert groups.validate_parent(session, None, 2, "topic") == 2
    session.scalars.assert_called_once()


def test_create_update_and_serialization():
    session = session_with_topics()
    group = groups.create_group(session, "Nowy", "topic", parent_id=2)
    assert groups.group_to_dict(group)["parent_id"] == 2
    groups.update_group(session, group, name="Nowa nazwa")
    assert group.parent_id == 2
    groups.update_group(session, group, parent_id=None)
    assert group.parent_id is None


def test_ancestors_and_rendering():
    assert groups.topic_ancestors(CATALOG, 3) == [2, 1]
    assert groups.topic_ancestors(CATALOG, 99) == []
    assert groups.render_catalog_tree([{"id": 1, "name": "A"}, {"id": 2, "name": "B", "parent_id": 99}]) == ""
    catalog = [*reversed(CATALOG), {"id": 5, "name": "algorytmy", "parent_id": 1}]
    assert groups.render_catalog_tree(catalog) == (
        "- Informatyka (id 1)\n  - algorytmy (id 5)\n  - Web development (id 2)\n"
        "    - React (id 3)\n- Zoologia (id 4)"
    )


@pytest.mark.parametrize("candidates,existing,dropped", [
    ([1, 2], [], {1}), ([1], [2], {1}), ([2, 4], [], set()),
    ([1, 2, 3], [], {1, 2}), ([1, 4], [3], {1}), ([2], [2], set()),
])
def test_drop_ancestor_suggestions(candidates, existing, dropped):
    assert suggestions.drop_ancestor_suggestions(candidates, existing, CATALOG) == dropped


def test_catalog_only_includes_parent_when_set():
    assert suggestions.active_topic_catalog(session_with_topics()) == CATALOG


def test_build_request_exposes_tree():
    template = prompt_templates.ResolvedTemplate(None, "test", None, "{{ catalog_tree }}")
    built = suggestions.build_request("document", Document(id=1), "test", CATALOG, template)
    assert built["prompt"] == groups.render_catalog_tree(CATALOG)


@pytest.mark.parametrize("target_type", ["feed_item", "document"])
@pytest.mark.parametrize("existing", [[], [3]])
def test_job_drops_ancestors_before_creating_rows(monkeypatch, target_type, existing):
    session = MagicMock()
    model = FeedItem if target_type == "feed_item" else Document
    target = model(id=10)
    run = ContentGroupSuggestionRun(id=20, model="test", catalog_snapshot=CATALOG)
    session.get.side_effect = lambda cls, key: target if cls is model else run
    session.scalars.return_value.all.return_value = existing
    monkeypatch.setattr(suggestions, "_config", lambda name, fallback=None: fallback)
    monkeypatch.setattr(suggestions, "supports_structured_output", lambda model: False)
    monkeypatch.setattr(suggestions, "ai_ask", lambda *args, **kwargs: SimpleNamespace(response_text=json.dumps({
        "suggestions": [{"group_id": gid, "confidence": 0.7, "reason": "pasuje"} for gid in [1, 2]],
        "no_match": False,
    })))
    result = suggestions.execute_suggestion_job(session, Job(id="job", parameters={f"{target_type}_id": 10, "run_id": 20}))
    added = [call.args[0] for call in session.add.call_args_list if isinstance(call.args[0], ContentGroupSuggestion)]
    assert [item.group_id for item in added] == ([] if existing else [2])
    assert result["suggestions"] == len(added)
    query = str(session.scalars.call_args.args[0])
    assert "content_groups.archived_at IS NULL" in query
    assert f"{target_type}_id" in query


def compiled(statement):
    return statement.compile(dialect=postgresql.dialect())


def test_archive_reparents_children():
    session = MagicMock()
    session.scalar.return_value = 0
    group = ContentGroup(id=2, parent_id=1)
    groups.archive_group(session, group)
    statement = compiled(session.execute.call_args.args[0])
    assert "UPDATE content_groups SET parent_id=" in str(statement)
    assert statement.params == {"parent_id": 1, "parent_id_1": 2}
    assert group.archived_at is not None


def test_merge_reparents_children_and_lifts_target():
    session = MagicMock()
    source = ContentGroup(id=2, parent_id=1, kind="topic")
    target = ContentGroup(id=3, parent_id=2, kind="topic")
    groups.merge_groups(session, source, target)
    statement = compiled(session.execute.call_args.args[0])
    assert "content_groups.id !=" in str(statement)
    assert statement.params == {"parent_id": 3, "parent_id_1": 2, "id_1": 3}
    assert target.parent_id == 1


@pytest.mark.parametrize("method", ["post", "patch"])
def test_routes_accept_parent_id_and_report_validation_errors(monkeypatch, method):
    app = Flask(__name__)
    app.register_blueprint(feed_routes.bp)

    @app.before_request
    def auth():
        g.auth = SimpleNamespace(kind="user", user_id=1)

    session = MagicMock()
    group = ContentGroup(id=2, name="Web", kind="topic", parent_id=1)
    session.get.return_value = group
    monkeypatch.setattr(feed_routes, "get_scoped_session", lambda: session)
    monkeypatch.setattr(feed_routes, "group_to_dict", lambda row, session=None: {"parent_id": row.parent_id})
    action = MagicMock(return_value=group)
    monkeypatch.setattr(feed_routes, "create_group" if method == "post" else "update_group", action)
    client = app.test_client()
    request = getattr(client, method)
    path = "/content_groups" if method == "post" else "/content_groups/2"
    response = request(path, json={"name": "Web", "kind": "topic", "parent_id": 1})
    assert response.status_code == (201 if method == "post" else 200)
    assert action.call_args.kwargs["parent_id"] == 1
    assert response.json == {"parent_id": 1}
    action.side_effect = ValueError("a topic cannot be its own ancestor")
    response = request(path, json={"parent_id": 2})
    assert response.status_code == 400
    assert "a topic cannot be its own ancestor" in response.get_data(as_text=True)
    session.rollback.assert_called_once()
