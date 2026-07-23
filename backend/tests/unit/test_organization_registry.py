"""Unit tests for library/organization_registry.py — global orgName registry.

docs/organization-ner-alias-plan.md reference case: document 9267, "Interia"
(count 2, variants Interii/Interią) + "Interii" (count 2) must merge into one
organization with mention_count 4.
"""

from unittest.mock import MagicMock

import pytest

pytest.importorskip("sqlalchemy")

from library.organization_registry import (  # noqa: E402
    AliasConflictError,
    add_alias,
    merge,
    merge_ner_groups,
    normalize_alias,
    resolve_alias,
)


def _execute_result(first=None, all_=None, scalar=None):
    result = MagicMock()
    result.scalars.return_value.first.return_value = first
    result.scalars.return_value.all.return_value = all_ or ([] if first is None else [first])
    result.scalar.return_value = scalar
    return result


class TestMergeNerGroups:
    def test_reference_case_interia_interii(self):
        groups = {
            "Interia": {"count": 2, "variants": ["Interii", "Interią"]},
            "Interii": {"count": 2, "variants": ["Interii"]},
        }
        merged = merge_ner_groups(groups)
        assert len(merged) == 1
        (name, group), = merged.items()
        assert name == "Interia"
        assert group["count"] == 4
        assert set(group["variants"]) == {"Interii", "Interią"}

    def test_no_overlap_keeps_groups_separate(self):
        groups = {
            "Interia": {"count": 2, "variants": ["Interii"]},
            "NATO": {"count": 1, "variants": []},
        }
        merged = merge_ner_groups(groups)
        assert merged.keys() == {"Interia", "NATO"}
        assert merged["Interia"]["count"] == 2
        assert merged["NATO"]["count"] == 1

    def test_transitive_three_way_merge(self):
        # C overlaps with B only, B overlaps with A only — must still merge all three.
        groups = {
            "Alfa": {"count": 1, "variants": ["Alfa Beta"]},
            "Alfa Beta": {"count": 1, "variants": ["Alfa Beta Gamma"]},
            "Gamma": {"count": 1, "variants": ["Alfa Beta Gamma"]},
        }
        merged = merge_ner_groups(groups)
        assert len(merged) == 1
        (_name, group), = merged.items()
        assert group["count"] == 3

    def test_canonical_name_excluded_from_its_own_variants(self):
        groups = {"Interia": {"count": 2, "variants": ["Interii", "Interią"]}}
        merged = merge_ner_groups(groups)
        (name, group), = merged.items()
        assert name == "Interia"
        assert "Interia" not in group["variants"]


class TestNormalizeAlias:
    def test_casefolds_without_stripping_diacritics(self):
        assert normalize_alias("Interią") == "interią"
        assert normalize_alias("  Interia  ") == "interia"


class TestResolveAlias:
    def test_matches_alias_table_first(self):
        fake_org = MagicMock(canonical_name="Interia")
        fake_alias = MagicMock(organization=fake_org)
        session = MagicMock()
        session.execute.return_value = _execute_result(first=fake_alias)

        result = resolve_alias(session, "Interii")

        assert result is fake_org
        assert session.execute.call_count == 1

    def test_falls_back_to_canonical_name(self):
        fake_org = MagicMock(canonical_name="Interia")
        session = MagicMock()
        session.execute.side_effect = [
            _execute_result(first=None),           # alias lookup miss
            _execute_result(all_=[fake_org]),        # canonical_name scan
        ]

        result = resolve_alias(session, "Interia")

        assert result is fake_org

    def test_no_match_returns_none(self):
        session = MagicMock()
        session.execute.side_effect = [
            _execute_result(first=None),
            _execute_result(all_=[]),
        ]
        assert resolve_alias(session, "Unknown Corp") is None


class TestAddAlias:
    def test_idempotent_for_same_organization(self):
        org = MagicMock(id=1)
        existing = MagicMock(organization_id=1)
        session = MagicMock()
        session.execute.return_value = _execute_result(first=existing)

        result = add_alias(session, org, "Interii")

        assert result is existing
        session.add.assert_not_called()

    def test_conflict_with_different_organization_raises(self):
        org = MagicMock(id=1)
        existing = MagicMock(organization_id=2)
        session = MagicMock()
        session.execute.return_value = _execute_result(first=existing)

        with pytest.raises(AliasConflictError) as exc_info:
            add_alias(session, org, "Interii")
        assert exc_info.value.existing_organization_id == 2

    def test_creates_new_alias(self):
        org = MagicMock(id=1)
        session = MagicMock()
        session.execute.return_value = _execute_result(first=None)

        row = add_alias(session, org, "Interii", alias_kind="inflection", created_by="manual")

        session.add.assert_called_once()
        added = session.add.call_args.args[0]
        assert added.alias == "Interii"
        assert added.alias_kind == "inflection"
        assert added.created_by == "manual"
        assert row is added


class TestMerge:
    def test_source_and_target_must_differ(self):
        session = MagicMock()
        with pytest.raises(ValueError):
            merge(session, 1, 1)

    def test_missing_organization_raises_lookup_error(self):
        session = MagicMock()
        session.get.side_effect = [None, MagicMock()]
        with pytest.raises(LookupError):
            merge(session, 1, 2)

    def test_repoints_links_and_deletes_orphaned_source(self):
        source = MagicMock(id=1, canonical_name="Interii", aliases=[])
        target = MagicMock(id=2, canonical_name="Interia")
        session = MagicMock()
        session.get.side_effect = lambda model, id_: {1: source, 2: target}[id_]

        link = MagicMock(document_id=42, organization_id=1)
        # add_alias(): no existing alias conflict
        # merge(): source_links query, then per-link "already on target" check,
        # then remaining-links count for orphan check (0 -> delete)
        session.execute.side_effect = [
            _execute_result(first=None),        # add_alias: no conflict
            _execute_result(all_=[link]),        # source_links
            _execute_result(first=None),         # no existing target link for this document
            _execute_result(scalar=0),           # remaining links count (orphan check)
        ]

        result = merge(session, 1, 2, make_global_alias=True)

        assert result["organization_id"] == 2
        assert result["canonical_name"] == "Interia"
        assert link.organization_id == 2  # re-pointed, not dropped as duplicate
        session.delete.assert_called_with(source)
        assert result["source_organization_deleted"] is True

    def test_duplicate_document_link_is_dropped_not_repointed(self):
        source = MagicMock(id=1, canonical_name="Interii", aliases=[])
        target = MagicMock(id=2, canonical_name="Interia")
        session = MagicMock()
        session.get.side_effect = lambda model, id_: {1: source, 2: target}[id_]

        source_link = MagicMock(document_id=42, organization_id=1)
        target_link_already_exists = MagicMock(document_id=42, organization_id=2)
        session.execute.side_effect = [
            # make_global_alias=False -> add_alias() is never called, no conflict-check execute
            _execute_result(all_=[source_link]),                 # source_links
            _execute_result(first=target_link_already_exists),   # target already linked for this doc
            _execute_result(scalar=1),                           # remaining links count -> not orphaned
        ]

        result = merge(session, 1, 2, make_global_alias=False)

        session.delete.assert_any_call(source_link)
        assert result["source_organization_deleted"] is False
