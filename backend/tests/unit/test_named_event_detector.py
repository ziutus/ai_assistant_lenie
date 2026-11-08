import pytest

from library.named_event_detector import detect_named_events


def test_organization_lookup_repairs_typo():
    def lookup(phrase):
        assert phrase == "Cambridge Analitica"
        return "Cambridge Analytica", 1239

    assert detect_named_events("(afera Cambridge Analitica)", lookup) == {
        "afera Cambridge Analytica": {
            "count": 1, "variants": ["afera Cambridge Analitica"], "organization_id": 1239,
        },
    }


@pytest.mark.parametrize("text,name", [
    ("aferą Watergate", "afera Watergate"),
    ("skandalu Enron", "skandal Enron"),
    ("Aferze Łódź-Nowa\u00a0Alpha Beta Gamma Delta", "afera Łódź-Nowa\u00a0Alpha Beta Gamma"),
])
def test_inflections_unicode_and_four_word_limit(text, name):
    assert list(detect_named_events(text)) == [name]


@pytest.mark.parametrize("text", ["afera mała", "Afera.", "skandal AB", "afera  Watergate", "afera. Enron",
                                       "superafera Enron", "afera\nEnron"])
def test_non_names_are_ignored(text):
    assert detect_named_events(text) == {}


def test_counts_and_unique_surface_variants():
    assert detect_named_events("aferą Watergate, afery Watergate, aferą Watergate") == {
        "afera Watergate": {
            "count": 3, "variants": ["aferą Watergate", "afery Watergate"], "organization_id": None,
        },
    }
