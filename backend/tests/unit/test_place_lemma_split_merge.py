from library.entity_service import _merge_lemma_split_places


def test_inflected_group_folds_into_group_listing_it_as_variant():
    groups = {
        ("placeName", "Aden"): {"count": 5, "variants": ["Adenu", "Aden"]},
        ("placeName", "Adenu"): {"count": 1, "variants": ["Adenu"]},
        ("placeName", "Mekka"): {"count": 1, "variants": ["Mekki"]},
        ("placeName", "Mekki"): {"count": 1, "variants": ["Mekki"]},
        ("orgName", "Texas"): {"count": 1, "variants": []},
        ("placeName", "Teksas"): {"count": 7, "variants": ["Teksasu"]},
        ("placeName", "Teksasu"): {"count": 1, "variants": ["Teksasu"]},
    }
    removed = _merge_lemma_split_places(groups)
    assert set(removed) == {("placeName", "Adenu"), ("placeName", "Mekki"), ("placeName", "Teksasu")}
    assert groups[("placeName", "Aden")]["count"] == 6
    assert groups[("placeName", "Teksas")]["count"] == 8
    assert groups[("placeName", "Mekka")]["count"] == 2
    assert ("orgName", "Texas") in groups


def test_unrelated_and_other_type_groups_are_kept():
    groups = {
        ("placeName", "Paryż"): {"count": 2, "variants": ["Paryżu"]},
        ("persName", "Paryżu"): {"count": 1, "variants": []},
        ("placeName", "Lyon"): {"count": 1, "variants": []},
    }
    assert _merge_lemma_split_places(groups) == []
    assert len(groups) == 3
