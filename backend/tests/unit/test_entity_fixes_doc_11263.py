"""Generic NER fixes found on doc #11263 (Yemen): acronym counts, person = place, Saudi and American demonyms."""

import pytest

pytest.importorskip("sqlalchemy")

from library.entity_service import _drop_persons_named_like_places, filter_entities_to_text
from library.ner_normalization import canonical_country_for_demonym_pattern


def org(text, variants=()):
    return {"id": 1, "text": text, "count": 17, "variants": list(variants)}


class TestAcronymsAreWholeWords:
    def test_natomiast_is_not_nato(self):
        text = "Natomiast Huti atakują. Natomiast Saudowie milczą. natomiast koniec."
        assert filter_entities_to_text({"orgName": [org("NATO")]}, text)["orgName"] == []

    def test_real_mentions_are_counted_and_the_look_alike_is_not(self):
        text = "Natomiast NATO milczy, a w NATO-wskich kręgach Natomiast nikt nie mówi. Rada NATO obradowała."
        kept = filter_entities_to_text({"orgName": [org("NATO")]}, text)["orgName"]
        # "NATO milczy", "NATO-wskich" (an adjective made from the acronym) and "Rada NATO"; never "Natomiast"
        assert [item["count"] for item in kept] == [3]

    def test_a_capitalised_word_is_not_an_acronym(self):
        # "Iran" without variants keeps the legacy word-start fallback (inflected forms are found)
        kept = filter_entities_to_text({"placeName": [org("Iran")]}, "W Iranie jest gorąco.")["placeName"]
        assert [item["count"] for item in kept] == [1]

    def test_acronym_with_variants_still_matches_its_variants(self):
        kept = filter_entities_to_text({"orgName": [org("UNHCR", ["UNHCR"])]}, "Agencja UNHCR ostrzega.")["orgName"]
        assert [item["count"] for item in kept] == [1]


class TestPersonNamedLikeAPlace:
    @staticmethod
    def groups():
        return {
            ("persName", "Marib"): {"count": 3, "variants": ["Marib"], "raw_lemmas": ["Marib"]},
            ("geogName", "Marib"): {"count": 3, "variants": ["Marib"], "raw_lemmas": ["Marib"]},
            ("persName", "Sana"): {"count": 2, "variants": ["Sanę", "Sana"]},
            ("placeName", "Sana"): {"count": 3, "variants": ["Sanę"]},
            ("persName", "Jordan"): {"count": 5, "variants": ["Jordan"]},
            ("placeName", "Jordan"): {"count": 2, "variants": ["Jordan"]},
            ("persName", "Joe Biden"): {"count": 2, "variants": ["Joe Biden"]},
            ("placeName", "Joe Biden"): {"count": 1, "variants": ["Joe Biden"]},
            ("persName", "Hadi"): {"count": 1, "variants": ["Hadi"]},
        }

    def test_one_word_person_with_the_spelling_of_a_place_is_folded_into_the_place(self):
        groups = self.groups()
        assert sorted(_drop_persons_named_like_places(groups)) == ["Marib", "Sana"]
        assert ("persName", "Marib") not in groups and ("persName", "Sana") not in groups
        assert groups[("geogName", "Marib")]["count"] == 6
        assert groups[("placeName", "Sana")]["count"] == 5
        assert groups[("placeName", "Sana")]["variants"] == ["Sanę", "Sana"]

    def test_a_person_mentioned_more_often_than_the_place_is_kept(self):
        groups = self.groups()
        _drop_persons_named_like_places(groups)
        assert ("persName", "Jordan") in groups and groups[("placeName", "Jordan")]["count"] == 2

    def test_full_names_and_unrelated_persons_are_never_touched(self):
        groups = self.groups()
        _drop_persons_named_like_places(groups)
        assert ("persName", "Joe Biden") in groups and ("persName", "Hadi") in groups

    def test_diacritics_do_not_hide_the_match(self):
        groups = {("persName", "Dżauf"): {"count": 1, "variants": []}, ("placeName", "Dzauf"): {"count": 2, "variants": []}}
        assert _drop_persons_named_like_places(groups) == ["Dżauf"]

    def test_nothing_to_do_without_places(self):
        groups = {("persName", "Hadi"): {"count": 1, "variants": ["Hadi"]}}
        assert _drop_persons_named_like_places(groups) == [] and ("persName", "Hadi") in groups


@pytest.mark.parametrize("surface,country", [
    ("Saudów", "Arabia Saudyjska"), ("Saudowie", "Arabia Saudyjska"), ("Saudom", "Arabia Saudyjska"),
    ("Saudowa", "Arabia Saudyjska"),
    ("Amerykański", "Stany Zjednoczone"), ("Amerykańscy", "Stany Zjednoczone"), ("Amerykańskiego", "Stany Zjednoczone"),
    ("Amerykanie", "Stany Zjednoczone"),
])
def test_demonyms_map_to_their_country(surface, country):
    assert canonical_country_for_demonym_pattern(surface) == country


@pytest.mark.parametrize("surface", ["Saudi", "Sauron", "Amerykańskość", "Amerykana", "Saudowski"])
def test_look_alikes_stay_unmapped_by_the_new_patterns(surface):
    assert canonical_country_for_demonym_pattern(surface) is None
