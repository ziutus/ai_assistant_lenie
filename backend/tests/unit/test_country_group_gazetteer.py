"""Named groups of states found in text (doc #10872: "państwa bałtyckie")."""

import pytest

pytest.importorskip("unidecode")

from library.country_gazetteer import canonical_country_name  # noqa: E402
from library.country_group_gazetteer import _GROUP_DATA, detect_country_groups, group_members  # noqa: E402

SENTENCE = ("Finlandia i państwa bałtyckie oprócz bycia członkami NATO włączonymi w planowanie nuklearne sojuszu "
            "dołączyły lub planują dołączyć do inicjatywy prezydenta Macrona")


def test_baltic_states_found_with_members_and_surface_form():
    (group,) = detect_country_groups(SENTENCE)
    assert group == {"name": "Państwa bałtyckie", "members": ["Litwa", "Łotwa", "Estonia"],
                     "variants": ["państwa bałtyckie"], "count": 1}


def test_inflected_and_repeated_mentions_are_counted_per_surface_form():
    (group,) = detect_country_groups("Państwa bałtyckie boją się. Pomoc dla państw bałtyckich. Państwa bałtyckie.")
    assert group["count"] == 3
    assert sorted(group["variants"]) == ["Państwa bałtyckie", "państw bałtyckich"]


def test_a_longer_phrase_is_not_counted_twice_by_its_shorter_pattern():
    (group,) = detect_country_groups("Rozmowy z państwami Zatoki Perskiej.")
    assert group["name"] == "Państwa Zatoki Perskiej"
    assert group["count"] == 1


@pytest.mark.parametrize("text", ["", "Morze Bałtyckie jest płytkie.", "Litwa, Łotwa i Estonia.", "państwo kryzys"])
def test_no_group_without_a_group_phrase(text):
    assert detect_country_groups(text) == []


def test_every_member_is_a_known_country():
    for name, members, _patterns in _GROUP_DATA:
        for member in members:
            assert canonical_country_name(member) == member, (name, member)
    assert group_members("Beneluks") == ("Belgia", "Holandia", "Luksemburg")
    assert group_members("brak") == ()
