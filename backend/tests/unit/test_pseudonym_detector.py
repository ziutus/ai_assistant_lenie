"""Explicit pseudonym patterns, without database or network."""

import pytest

from library.pseudonym_detector import PSEUDONYM_CUES, detect_pseudonyms


@pytest.mark.parametrize("quotes", ['"{}"', '„{}”', '“{}”', '«{}»', "'{}'"])
@pytest.mark.parametrize("cue", PSEUDONYM_CUES)
def test_cues_and_quotes(quotes, cue):
    surface = f'Andrij Osipow, {cue.upper()}: {quotes.format("Kryminał")}'
    assert detect_pseudonyms("Tak w tej historii pojawia się " + surface) == [
        {"person": "Andrij Osipow", "pseudonym": "Kryminał", "surface": surface},
    ]


@pytest.mark.parametrize("name", ["Andrija Osipowa", "Michał Zabdyr-Jamróz", "Émile Zola", "Jan Adam Nowak",
                                  "Jan Adam Piotr Nowak", "Andrij\u00a0Osipow"])
def test_names_and_parenthesis(name):
    assert detect_pseudonyms(f'{name} (ps. „Lis”)')[0]["person"] == name


def test_order_and_duplicates():
    pairs = detect_pseudonyms('Jan Nowak ps. "Lis"; Adam Kowalski vel «Wilk». Jan Nowak ps. "LIS"')
    assert [(p["person"], p["pseudonym"]) for p in pairs] == [("Jan Nowak", "Lis"), ("Adam Kowalski", "Wilk")]


@pytest.mark.parametrize("text", [
    "P.S. Pamiętaj", 'Jan Nowak\nP.S. "Lis"', 'Jan Nowak ps. Kryminał', 'Osipow ps. "Kryminał"',
    'andrij osipow ps. "Kryminał"', 'Jan Nowak ps. "jeden dwa trzy cztery pięć"',
    'Jan Nowak ps. "nowak"', 'Jan Nowak ps. "X"', 'Jan Nowak ps. ""',
    'Jan Nowak ps. "' + "x" * 41 + '"', 'Jan Nowak ps. "dwa\nwiersze"',
    'Jan Nowak ps. «Lis”',
])
def test_rejections(text):
    assert detect_pseudonyms(text) == []


def test_declined_name_in_parentheses_with_declined_cue():
    text = 'W maju zginął Andrija Osipowa (znanego jako „Kryminał”) w maju.'
    assert detect_pseudonyms(text) == [
        {"person": "Andrija Osipowa", "pseudonym": "Kryminał",
         "surface": 'Andrija Osipowa (znanego jako „Kryminał”'},
    ]
