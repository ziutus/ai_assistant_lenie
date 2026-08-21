"""Unit tests for library/ner_corrections.py — Faza 6 human-curated correction dictionary."""

from unittest.mock import MagicMock

import pytest

pytest.importorskip("sqlalchemy")

from library.ner_corrections import apply_ner_corrections  # noqa: E402


def _rule(match_lemma, corrected_text, *, id=1, match_entity_type="*", corrected_entity_type=None,
          scope="global", author=None):
    rule = MagicMock()
    rule.id = id
    rule.match_lemma = match_lemma
    rule.match_entity_type = match_entity_type
    rule.corrected_text = corrected_text
    rule.corrected_entity_type = corrected_entity_type
    rule.scope = scope
    rule.author = author
    return rule


def _session(rules):
    session = MagicMock()
    session.execute.return_value.scalars.return_value.all.return_value = rules
    return session


class TestApplyNerCorrections:
    def test_no_rules_leaves_groups_untouched(self):
        session = _session([])
        groups = {("orgName", "siła Zbrojny Sudan"): {"count": 1, "variants": ["Sił Zbrojnych Sudanu"],
                                                        "raw_lemmas": ["siła Zbrojny Sudan"]}}
        apply_ner_corrections(session, 9394, groups, None)
        assert groups == {("orgName", "siła Zbrojny Sudan"): {
            "count": 1, "variants": ["Sił Zbrojnych Sudanu"], "raw_lemmas": ["siła Zbrojny Sudan"],
        }}
        session.add_all.assert_not_called()

    def test_matches_by_raw_lemma_and_renames(self):
        rule = _rule("siła Zbrojny Sudan", "Siły Zbrojne Sudanu")
        session = _session([rule])
        groups = {
            ("orgName", "Siłami Zbrojnymi Sudan"): {
                "count": 1, "variants": ["Siłami Zbrojnymi Sudanu"], "raw_lemmas": ["siła Zbrojny Sudan"],
            },
        }
        apply_ner_corrections(session, 9394, groups, None)
        assert groups == {
            ("orgName", "Siły Zbrojne Sudanu"): {
                "count": 1, "variants": ["Siłami Zbrojnymi Sudanu"], "raw_lemmas": ["siła Zbrojny Sudan"],
            },
        }
        applied = session.add_all.call_args.args[0]
        assert len(applied) == 1
        assert applied[0].correction_id == rule.id
        assert applied[0].entity_text_before == "Siłami Zbrojnymi Sudan"
        assert applied[0].entity_text_after == "Siły Zbrojne Sudanu"

    def test_correction_can_retype_orgname_to_placename(self):
        rule = _rule("wielki Brytania", "Wielka Brytania", corrected_entity_type="placeName")
        session = _session([rule])
        groups = {("orgName", "wielki Brytania"): {"count": 1, "variants": ["Wielkiej Brytanii"],
                                                     "raw_lemmas": ["wielki Brytania"]}}
        apply_ner_corrections(session, 1, groups, None)
        assert ("placeName", "Wielka Brytania") in groups
        assert ("orgName", "wielki Brytania") not in groups

    def test_collision_merges_into_existing_target_group(self):
        rule = _rule("siła Zbrojny Sudan", "Siły Zbrojne Sudanu")
        session = _session([rule])
        groups = {
            ("orgName", "Siły Zbrojne Sudanu"): {
                "count": 27, "variants": ["SAF"], "raw_lemmas": ["Siły zbrojny Sudan"],
            },
            ("orgName", "Siłami Zbrojnymi Sudan"): {
                "count": 1, "variants": ["Siłami Zbrojnymi Sudanu"], "raw_lemmas": ["siła Zbrojny Sudan"],
            },
        }
        apply_ner_corrections(session, 9394, groups, None)
        assert groups == {
            ("orgName", "Siły Zbrojne Sudanu"): {
                "count": 28,
                "variants": ["SAF", "Siłami Zbrojnymi Sudanu"],
                "raw_lemmas": ["Siły zbrojny Sudan", "siła Zbrojny Sudan"],
            },
        }

    def test_entity_type_filter_does_not_cross_apply(self):
        """A rule scoped to placeName must not match an orgName group even
        with an identical lemma string."""
        rule = _rule("wielki Brytania", "Wielka Brytania", match_entity_type="placeName")
        session = _session([rule])
        groups = {("orgName", "wielki Brytania"): {"count": 1, "variants": [], "raw_lemmas": ["wielki Brytania"]}}
        apply_ner_corrections(session, 1, groups, None)
        assert groups == {("orgName", "wielki Brytania"): {"count": 1, "variants": [], "raw_lemmas": ["wielki Brytania"]}}
        session.add_all.assert_not_called()

    def test_geogname_and_placename_rule_are_interchangeable(self):
        rule = _rule("cieśnina Ormuz", "Cieśnina Ormuz", match_entity_type="geogName")
        session = _session([rule])
        groups = {("placeName", "cieśnina Ormuz"): {"count": 1, "variants": [], "raw_lemmas": ["cieśnina Ormuz"]}}
        apply_ner_corrections(session, 1, groups, None)
        assert ("placeName", "Cieśnina Ormuz") in groups

    def test_author_scoped_rule_only_applies_to_matching_author(self):
        rule = _rule("bad lemma", "Fixed Name", scope="author", author="Podcast X")
        session = _session([rule])

        groups_other_author = {("orgName", "bad lemma"): {"count": 1, "variants": [], "raw_lemmas": ["bad lemma"]}}
        apply_ner_corrections(session, 1, groups_other_author, "Someone Else")
        assert ("orgName", "bad lemma") in groups_other_author  # untouched

        groups_matching_author = {("orgName", "bad lemma"): {"count": 1, "variants": [], "raw_lemmas": ["bad lemma"]}}
        apply_ner_corrections(session, 1, groups_matching_author, "Podcast X")
        assert ("orgName", "Fixed Name") in groups_matching_author

    def test_no_matching_rule_leaves_group_untouched(self):
        rule = _rule("something else", "Irrelevant")
        session = _session([rule])
        groups = {("orgName", "siła Zbrojny Sudan"): {"count": 1, "variants": [], "raw_lemmas": ["siła Zbrojny Sudan"]}}
        apply_ner_corrections(session, 1, groups, None)
        assert ("orgName", "siła Zbrojny Sudan") in groups
        session.add_all.assert_not_called()
