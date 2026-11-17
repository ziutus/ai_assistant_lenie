"""Text-only vessel detection and its deliberate token boundaries."""

import pytest

from library.named_vessel_detector import VESSEL_INDICATORS, detect_named_vessels


@pytest.mark.parametrize(
    "text,name,phrase",
    [
        ("Mamy już lotniskowiec Teodor Rooswelt.", "lotniskowiec Teodor Rooswelt", "Teodor Rooswelt"),
        ("lotniskowca Teodora Rooswelta", "lotniskowiec Teodora Rooswelta", "Teodora Rooswelta"),
        ("okręt podwodny USS Virginia", "okręt USS Virginia", "USS Virginia"),
        ("niszczyciel USS Cole", "niszczyciel USS Cole", "USS Cole"),
        ("fregata ORP Gen. Kazimierz Pulaski", "fregata ORP Gen", "ORP Gen"),
        ("fregata ORP Kazimierz Pulaski Dalej", "fregata ORP Kazimierz Pulaski", "ORP Kazimierz Pulaski"),
        ("okręt\u00a0USS\u00a0Virginia", "okręt USS\u00a0Virginia", "USS\u00a0Virginia"),
    ],
)
def test_names(text, name, phrase):
    result = detect_named_vessels(text)
    assert list(result) == [name]
    surface = text.removeprefix("Mamy już ")
    surface = surface[: surface.index(phrase) + len(phrase)]
    assert result[name] == {"count": 1, "variants": [surface], "phrase": phrase}


@pytest.mark.parametrize("form,lemma", VESSEL_INDICATORS.items())
def test_all_inflections(form, lemma):
    assert detect_named_vessels(f"{form.upper()} Virginia") == {
        f"{lemma} Virginia": {"count": 1, "variants": [f"{form.upper()} Virginia"], "phrase": "Virginia"},
    }


def test_grouping_and_unique_surface_order():
    assert detect_named_vessels("lotniskowiec USS Cole; LOTNISKOWCA USS COLE; lotniskowiec USS Cole") == {
        "lotniskowiec USS Cole": {
            "count": 3,
            "variants": ["lotniskowiec USS Cole", "LOTNISKOWCA USS COLE"],
            "phrase": "USS Cole",
        },
    }


@pytest.mark.parametrize(
    "text",
    [
        "okręt jest duży",
        "lotniskowiec",
        "Okręt",
        "lotniskowiec płynie do Zatoki",
        "Roosevelt przemówił",
        "nadokręt Virginia",
        "okręt AB",
        "okręt  Virginia",
        "okręt\nVirginia",
        "okręt podwodny atomowy Virginia",
        "okręt nowy Virginia",
        "okręt podwodnY Virginia",
    ],
)
def test_no_name(text):
    assert detect_named_vessels(text) == {}
