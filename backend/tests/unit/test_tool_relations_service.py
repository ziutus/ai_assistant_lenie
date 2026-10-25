from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

pytest.importorskip("sqlalchemy")

from library import tool_relations_service as svc


def _tool(id_, name, status="watchlist", **extra):
    base = dict(id=id_, name=name, status=status, description=None, source_context=None, source_document_id=None)
    base.update(extra)
    return SimpleNamespace(**base)


def _session(others, existing_edge=None):
    session = MagicMock()
    others_result = MagicMock()
    others_result.scalars.return_value.all.return_value = others
    edge_result = MagicMock()
    edge_result.scalars.return_value.first.return_value = existing_edge
    session.execute.side_effect = [others_result] + [edge_result] * len(others)
    return session


class TestNamePattern:
    def test_short_names_are_case_sensitive(self):
        pattern = svc._name_pattern("AWS")
        assert pattern.search("emulates AWS, Azure")
        assert not pattern.search("laws and aws-cli")
        assert not pattern.search("raws")

    def test_long_names_ignore_case_but_need_whole_words(self):
        pattern = svc._name_pattern("Terraform")
        assert pattern.search("dry runs of terraform and OpenTofu")
        assert not pattern.search("terraformer")

    def test_too_short_names_never_match(self):
        assert svc._name_pattern("Go") is None


class TestDetectRelations:
    def test_proposes_edges_to_tools_named_in_the_description(self):
        item = _tool(1, "Floci", description="Local emulators of AWS, Azure and GCP; works with Terraform.")
        others = [_tool(2, "AWS", "adopted"), _tool(3, "Terraform"), _tool(4, "Kubernetes")]
        session = _session(others)

        outcome = svc.detect_relations(session, item)

        assert outcome["created"] == ["AWS", "Terraform"]
        added = [call.args[0] for call in session.add.call_args_list]
        assert {(e.from_tool_id, e.to_tool_id, e.status) for e in added} == {(1, 2, "proposed"), (1, 3, "proposed")}
        assert "AWS" in added[0].context

    def test_existing_edge_is_not_duplicated_or_revived(self):
        item = _tool(1, "Floci", description="works with Terraform")
        session = _session([_tool(3, "Terraform")], existing_edge=SimpleNamespace(status="rejected"))

        outcome = svc.detect_relations(session, item)

        assert outcome == {"created": [], "existing": 1}
        session.add.assert_not_called()

    def test_no_source_text_makes_no_queries(self):
        session = MagicMock()
        assert svc.detect_relations(session, _tool(1, "Floci")) == {"created": [], "existing": 0}
        session.execute.assert_not_called()


class TestRelationsFor:
    def test_edge_is_rendered_from_both_perspectives_with_stack_flag(self):
        edge = SimpleNamespace(id=9, from_tool_id=1, to_tool_id=2, relation="works_with", status="proposed",
                               detected_by="name_match", context="…AWS…")
        session = MagicMock()
        edges = MagicMock()
        edges.scalars.return_value.all.return_value = [edge]
        entries = MagicMock()
        entries.scalars.return_value.all.return_value = [_tool(1, "Floci"), _tool(2, "AWS", "adopted")]
        session.execute.side_effect = [edges, entries]

        result = svc.relations_for(session, [1, 2])

        assert result[1][0]["other_name"] == "AWS" and result[1][0]["in_my_stack"] is True
        assert result[2][0]["other_name"] == "Floci" and result[2][0]["in_my_stack"] is False

    def test_edge_is_rendered_with_its_direction(self):
        edge = SimpleNamespace(id=9, from_tool_id=1, to_tool_id=2, relation="emulates", status="confirmed",
                               detected_by="name_match", context=None)
        session = MagicMock()
        edges = MagicMock()
        edges.scalars.return_value.all.return_value = [edge]
        entries = MagicMock()
        entries.scalars.return_value.all.return_value = [_tool(1, "Floci"), _tool(2, "AWS", "adopted")]
        session.execute.side_effect = [edges, entries]

        result = svc.relations_for(session, [1, 2])

        assert result[1][0]["direction"] == "out" and result[2][0]["direction"] == "in"

    def test_empty_input(self):
        assert svc.relations_for(MagicMock(), []) == {}


class TestRelationsForTools:
    """Catalog tools reach their relations through ToolRecommendation.tool_id, never through the name."""

    def test_relations_of_every_radar_entry_pointing_at_the_tool_are_merged_without_self_links(self, monkeypatch):
        gcp_a = _tool(10, "GCP", "adopted", tool_id=4)
        gcp_b = _tool(11, "GCP", "watchlist", tool_id=4)
        session = MagicMock()
        session.execute.return_value.scalars.return_value.all.return_value = [gcp_a, gcp_b]
        floci = {"id": 1, "other_id": 31, "other_name": "Floci"}
        duplicate = {"id": 1, "other_id": 31, "other_name": "Floci"}
        to_twin = {"id": 2, "other_id": 11, "other_name": "GCP"}  # an edge between two entries of the same tool
        monkeypatch.setattr(svc, "relations_for", lambda _s, ids: {10: [floci, to_twin], 11: [duplicate]})

        result = svc.relations_for_tools(session, [SimpleNamespace(id=4), SimpleNamespace(id=5)])

        assert result == {4: [floci]}

    def test_no_tools_no_query(self):
        session = MagicMock()
        assert svc.relations_for_tools(session, []) == {}
        session.execute.assert_not_called()
