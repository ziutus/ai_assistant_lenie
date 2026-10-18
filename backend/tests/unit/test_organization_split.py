"""Splitting an orgName made of glued mentions ("NATO Moskwa", doc #10872) and its replay."""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

pytest.importorskip("sqlalchemy")

from library.db.models import DocumentEntity, DocumentOrganization  # noqa: E402
from library.entity_overrides import (  # noqa: E402
    replay_manual_organization_decisions,
    split_organization_entity,
)

# Real sentence from doc #10872; spaCy returned "NATO Moskwa" as one orgName span.
SENTENCE = "W liście do NATO Moskwa wyraźnie wspomina tylko znowu proszę państwa nie wiadomo czy to jest list wysłany"
REGISTRY = {"NATO": (9, "NATO"), "Moskwa": (170, "Moskwa"), "Moskwy": (170, "Moskwa")}


def org_row(text, entity_id, count=1, variants=None, source="ner"):
    return DocumentEntity(
        id=entity_id, document_id=10872, entity_type="orgName", entity_text=text,
        mention_count=count, variants=variants or [], source=source,
    )


def resolve(session, name, forms=None):
    organization_id, canonical = REGISTRY[name]
    return SimpleNamespace(id=organization_id, canonical_name=canonical), "canonical_matched"


def make_session(links=()):
    session = MagicMock()
    session.scalars.return_value.all.return_value = list(links)
    session.scalar.return_value = None
    added = []
    session.add.side_effect = added.append
    return session, added


def split(entity, parts, entities, **kwargs):
    session, added = make_session()
    with patch("library.organization_registry.resolve_or_create", side_effect=resolve):
        results = split_organization_entity(session, entity, parts, entities, **kwargs)
    return session, added, results


def test_nato_moskwa_becomes_two_manual_organizations_with_links():
    assert "NATO Moskwa" in SENTENCE
    original = org_row("NATO Moskwa", 15887, count=2)
    entities = [original]
    session, added, results = split(original, ["NATO", "Moskwa"], entities)

    session.delete.assert_any_call(original)
    assert original not in entities
    assert [(row.entity_text, row.mention_count, row.source) for row, _ in results] == [
        ("NATO", 2, "manual"), ("Moskwa", 2, "manual")]
    assert [org.id for _, org in results] == [9, 170]
    links = [obj for obj in added if isinstance(obj, DocumentOrganization)]
    assert [(link.organization_id, link.confidence) for link in links] == [
        (9, "canonical_matched"), (170, "canonical_matched")]


def test_part_is_folded_into_an_existing_row_of_the_document():
    original = org_row("NATO Moskwa", 15887, count=2)
    nato = org_row("NATO", 15839, count=18)
    entities = [original, nato]
    _, added, results = split(original, ["NATO", "Moskwa"], entities)

    assert results[0][0] is nato
    assert (nato.mention_count, nato.source) == (20, "manual")
    assert [row.entity_text for row in entities] == ["NATO", "Moskwa"]
    assert not [obj for obj in added if isinstance(obj, DocumentEntity) and obj.entity_text == "NATO"]


def test_replay_style_fold_does_not_add_counts_twice():
    original = org_row("NATO Moskwa", 15887, count=2)
    nato = org_row("NATO", 15839, count=18)
    split(original, ["NATO", "Moskwa"], [original, nato], fold_counts=False)
    assert nato.mention_count == 18


def test_surface_forms_go_to_parts_word_by_word_under_the_canonical_name():
    original = org_row("Moskwy NATO", 1, count=1, variants=["Moskwę NATO"])
    registry = {"NATO": (9, "NATO"), "Moskwy": (170, "Moskwa"), "Moskwę": (170, "Moskwa")}
    session, added = make_session()
    with patch("library.organization_registry.resolve_or_create",
               side_effect=lambda s, name, forms=None: (SimpleNamespace(id=registry[name][0],
                                                                        canonical_name=registry[name][1]), "alias_matched")):
        results = split_organization_entity(session, original, ["Moskwy", "NATO"], [original])
    moscow = results[0][0]
    assert moscow.entity_text == "Moskwa"
    assert moscow.variants == ["Moskwy", "Moskwę"]


def test_existing_link_is_reused_not_duplicated():
    original = org_row("NATO Moskwa", 15887, count=2)
    session, added = make_session()
    existing = DocumentOrganization(document_id=10872, organization_id=9, document_entity_id=None)
    session.scalar.side_effect = [existing, None]
    with patch("library.organization_registry.resolve_or_create", side_effect=resolve):
        results = split_organization_entity(session, original, ["NATO", "Moskwa"], [original])
    links = [obj for obj in added if isinstance(obj, DocumentOrganization)]
    assert [link.organization_id for link in links] == [170]
    assert existing.document_entity_id == results[0][0].id


def decision(parts=("NATO", "Moskwa"), part_names=("NATO", "Moskwa"), text="NATO Moskwa"):
    return SimpleNamespace(decision="organization_split", entity_text=text, entity_type="orgName",
                           details={"parts": list(parts), "part_names": list(part_names)})


def replay(decisions, entities):
    session, added = make_session()
    session.scalars.return_value.all.side_effect = [decisions, entities, []]
    with patch("library.organization_registry.resolve_or_create", side_effect=resolve) as resolver:
        stats = replay_manual_organization_decisions(session, 10872)
    return session, added, stats, resolver


def test_replay_drops_the_glued_row_when_manual_parts_survived_the_refresh():
    glued = org_row("NATO Moskwa", 20001, count=2)
    nato = org_row("NATO", 15839, count=20, source="manual")
    moskwa = org_row("Moskwa", 15886, count=4, source="manual")
    entities = [glued, nato, moskwa]
    session, _, stats, resolver = replay([decision()], entities)

    assert stats == {"organization_split": 1}
    assert [call.args[0] for call in session.delete.call_args_list] == [glued]
    assert (nato.mention_count, moskwa.mention_count) == (20, 4)
    resolver.assert_not_called()


def test_replay_splits_again_when_everything_was_rebuilt():
    glued = org_row("NATO Moskwa", 20001, count=2)
    entities = [glued]
    _, added, stats, _ = replay([decision()], entities)

    assert stats == {"organization_split": 1}
    new_rows = [obj for obj in added if isinstance(obj, DocumentEntity)]
    assert sorted(row.entity_text for row in new_rows) == ["Moskwa", "NATO"]
    assert all(row.source == "manual" and row.mention_count == 2 for row in new_rows)
    assert len([obj for obj in added if isinstance(obj, DocumentOrganization)]) == 2


@pytest.mark.parametrize("decisions,entities", [
    ([decision()], []),
    ([decision(parts=["NATO"])], [org_row("NATO Moskwa", 1)]),
    ([], [org_row("NATO Moskwa", 1)]),
])
def test_replay_without_a_matching_mention_or_valid_parts_is_a_no_op(decisions, entities):
    session = MagicMock()
    session.scalars.return_value.all.side_effect = [decisions, entities]
    assert replay_manual_organization_decisions(session, 10872) == {}
    session.delete.assert_not_called()
