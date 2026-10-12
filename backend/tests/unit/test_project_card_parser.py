"""Tests for the project-card PDF parser (pure line parsing + a generated-PDF smoke test)."""

import csv

import pytest

pytest.importorskip("sqlalchemy")  # the importer round-trip test pulls in the ORM models

from library.project_card_parser import (
    flag_card,
    parse_card_dir,
    parse_lines,
    write_review_csv,
)
from library.project_cards import normalize_import_card

TITLE, TAGLINE, BODY, LABEL = 49.5, 21.0, 17.2, 11.2


def _card_lines(*, age="5-9", time="30 min", difficulty="Łatwy", steps=None, tools_after_footer=None):
    """Lines in the order the PDF text layer produces them for a card (modelled on card 001)."""
    steps = steps if steps is not None else [
        "Zrób dwa otwory w pudełku kartonowym, aby włożyć patyczek do szaszłyków.",
        "Połóż linijkę na patyczku do szaszłyków, upewniając się, że może się swobodnie",
        "obracać.",
        "Przyklej plastikowy kubeczek na każdym końcu linijki.",
    ]
    lines = [
        ("N I E S A M O W I T E M A S Z Y N Y", 16.5),
        ("D Ź W I G N I E I K O Ł Y S K I", 16.5),
        ("RÓWNOWAGA I CIĘŻAR", 13.5),
        ("Magiczna Waga z", TITLE), ("Kartonu", TITLE),
        ("Domowa waga pokazująca równowagę za pomocą codziennych", TAGLINE), ("przedmiotów.", TAGLINE),
        ("Zbuduj prostą wagę, aby zrozumieć, jak ciężar wpływa na równowagę.", BODY),
        ("◷", 22.5), ("W I E K", LABEL), (age, 19.5),
        ("C Z A S", LABEL), (time, 19.5),
        ("P O Z I O M T R U D N O Ś C I", LABEL), (difficulty, 19.5),
        ("M E C H A N I Z M", LABEL), ("Dźwignia /", 19.5), ("Silnik DC", 19.5),
        ("J A K T O D Z I A Ł A", LABEL),
        ("Linijka działa jak dźwignia obracająca się wokół patyczka do szaszłyków.", BODY),
        ("M A T E R I A Ł Y", LABEL),
        ("1", 14), ("Małe", 14), ("pudełko", 14), ("kartonowe", 14),
        ("1", 14), ("Linijka", 14),
        ("2", 14), ("Plastikowe", 14), ("kubeczki", 14),
        ("1", 14), ("Patyczek", 14), ("do", 14), ("szaszłykó", 14), ("w lub", 14), ("ołówek", 14),
        ("20 cm", 14), ("Cienka nić", 14),
        ("N A R Z Ę D Z I A", LABEL),
        ("K R O K I", LABEL),
    ]
    for index, text in enumerate(steps, start=1):
        if text and text[0].isupper():
            lines.append((f"{index:02d}", 20))
        lines.append((text, BODY))
    lines += [
        ("J E Ś L I N I E D Z I A Ł A", LABEL),
        ("⚠ Linijka się nie porusza.", 15), ("Upewnij się, że otwory są nieco większe.", 15),
        ("001 · Niesamowite Maszyny", 12),
    ]
    lines += tools_after_footer if tools_after_footer is not None else [
        ("nożyczki", 15), ("✚", 15), ("taśma klejąca", 15), ("✚", 15),
    ]
    lines += [
        ("B E Z P I E C Z E Ń S T W O", LABEL),
        ("Wymagany jest nadzór osoby dorosłej do robienia otworów. “", 15),
        ("W A R I A N T Y", LABEL),
        ("“", 15), ("Udekoruj wagę kolorami.", 15), ("✦", 15), ("Zważ różne przedmioty.", 15), ("✦", 15),
        ("D Ź W I G N I E I K O Ł Y S K I", 16.5), ("№ 001", 14),
    ]
    return lines


@pytest.fixture()
def card():
    return parse_lines(_card_lines(), number="001", filename="001 - Magiczna Waga z Kartonu.pdf",
                       page_pt=(810, 2069), images=1)


def test_header_and_top_block(card):
    assert card["number"] == "001" and card["images"] == 1 and card["page_pt"] == [810, 2069]
    assert card["series_raw"] == "NIESAMOWITEMASZYNY" and card["group_raw"] == "DŹWIGNIEIKOŁYSKI"
    assert card["topic"] == "RÓWNOWAGA I CIĘŻAR"
    assert card["title"] == "Magiczna Waga z Kartonu"
    assert card["tagline"].endswith("codziennych przedmiotów.")
    assert card["description"].startswith("Zbuduj prostą wagę")
    assert card["series_footer"] == "Niesamowite Maszyny"


def test_key_facts_are_parsed_into_numbers(card):
    assert (card["age_min"], card["age_max"]) == (5, 9)
    assert (card["time_min"], card["time_max"]) == (30, 30)
    assert card["difficulty"] == 1
    assert card["mechanism"] == "Dźwignia / Silnik DC"


@pytest.mark.parametrize("age, expected", [("6-10 lat", (6, 10)), ("7+", (7, None)), ("4–8", (4, 8)), ("brak", (None, None))])
def test_age_variants(age, expected):
    parsed = parse_lines(_card_lines(age=age), number="001")
    assert (parsed["age_min"], parsed["age_max"]) == expected


@pytest.mark.parametrize("time, expected", [("45 min", (45, 45)), ("1 godz", (60, 60)), ("20-30 min", (20, 30))])
def test_time_variants(time, expected):
    parsed = parse_lines(_card_lines(time=time), number="001")
    assert (parsed["time_min"], parsed["time_max"]) == expected


def test_materials_pair_quantity_with_wrapped_name_and_fix_broken_words(card):
    assert card["materials"] == [
        {"qty": "1", "name": "Małe pudełko kartonowe"},
        {"qty": "1", "name": "Linijka"},
        {"qty": "2", "name": "Plastikowe kubeczki"},
        {"qty": "1", "name": "Patyczek do szaszłyków lub ołówek"},
        {"qty": "20 cm", "name": "Cienka nić"},
    ]


def test_steps_join_wrapped_lines(card):
    assert len(card["steps"]) == 3
    assert card["steps"][1].endswith("się swobodnie obracać.")


def test_displaced_tools_after_footer_are_recovered(card):
    assert card["tools"] == ["nożyczki", "taśma klejąca"]
    assert card["troubleshooting"] == [
        {"problem": "Linijka się nie porusza.", "solution": "Upewnij się, że otwory są nieco większe."}
    ]


def test_multiline_tool_and_safety_and_variants(card):
    wrapped = parse_lines(
        _card_lines(tools_after_footer=[("Pistolet do kleju na gorąco (z pomocą", 15), ("dorosłego)", 15), ("✚", 15)]),
        number="001",
    )
    assert wrapped["tools"] == ["Pistolet do kleju na gorąco (z pomocą dorosłego)"]
    assert card["safety"] == "Wymagany jest nadzór osoby dorosłej do robienia otworów."
    assert card["variants"] == ["Udekoruj wagę kolorami.", "Zważ różne przedmioty."]
    assert card["needs_adult"] is True


def test_hyphen_split_words_are_rejoined():
    parsed = parse_lines(_card_lines(steps=["Zrób huśtawkę z Bu‐", "telek i połącz je ze sobą.", ""]), number="002")
    assert parsed["steps"][0] == "Zrób huśtawkę z Butelek i połącz je ze sobą."


def test_clean_card_has_no_flags(card):
    assert card["flags"] == []


def test_flags_step_uses_unlisted_item_and_hazards():
    lines = _card_lines(steps=["Przyklej dwie nakrętki do patyczka.", "Włącz silnik.", "Gotowe."],
                        tools_after_footer=[("nożyczki", 15), ("✚", 15)])
    parsed = parse_lines(lines, number="002")
    assert "step_uses_unlisted:nakrętka" in parsed["flags"]
    assert "step_uses_unlisted:silnik" in parsed["flags"]


def test_flag_card_adult_and_hazard_rules():
    base = {
        "title": "t", "tagline": "t", "description": "d", "how_it_works": "h", "safety": "",
        "materials": [{"qty": "1", "name": "nóż do tapet"}], "steps": ["a", "b", "c"], "tools": ["pistolet"],
        "variants": ["v"], "troubleshooting": [{"problem": "p", "solution": "s"}],
        "age_min": 3, "time_min": 90, "difficulty": 1, "needs_adult": False, "flags": [],
    }
    flag_card(base)
    assert any(f.startswith("hazard_no_adult") for f in base["flags"])
    assert "easy_but_long" in base["flags"] and "missing:safety" in base["flags"]
    silent = {**base, "needs_adult": True, "flags": [], "tools": ["klej (z pomocą dorosłego)"], "safety": "uwaga"}
    flag_card(silent)
    assert "adult_needed_young_age" in silent["flags"] and "adult_tool_but_safety_silent" in silent["flags"]
    aware = {**silent, "flags": [], "safety": "Potrzebny dorosły."}
    flag_card(aware)
    assert "adult_tool_but_safety_silent" not in aware["flags"]


def test_parsed_card_is_accepted_by_the_importer(card):
    imported = normalize_import_card(card)
    assert imported["number"] == 1 and imported["group_name"] == "Dźwignie i kołyski"
    assert imported["review_status"] == "imported" and imported["steps"] == card["steps"]


def test_write_review_csv(tmp_path, card):
    path = tmp_path / "review.csv"
    write_review_csv([card, {"number": "002", "file": "002.pdf", "flags": ["PARSE_ERROR:boom"]}], path)
    rows = list(csv.reader(path.open(encoding="utf-8-sig"), delimiter=";"))
    assert rows[0][0] == "nr" and rows[1][1] == "Magiczna Waga z Kartonu"
    assert rows[2][-1] == "PARSE_ERROR:boom"


def test_parse_card_dir_reports_unreadable_pdf_instead_of_aborting(tmp_path):
    pytest.importorskip("fitz")
    (tmp_path / "007 - Zepsuty.pdf").write_bytes(b"not a pdf")
    cards = parse_card_dir(tmp_path)
    assert cards[0]["number"] == "007" and cards[0]["flags"][0].startswith("PARSE_ERROR:")


def test_parse_card_pdf_reads_a_generated_page(tmp_path):
    fitz = pytest.importorskip("fitz")
    from library.project_card_parser import parse_card_pdf

    document = fitz.open()
    page = document.new_page(width=600, height=800)
    y = 40
    # the built-in PDF font has no Polish glyphs, so the generated page uses ASCII text
    for text, size in [("TEMAT", 13), ("Tytul Karty", 45), ("Krotki opis karty.", 21), ("W I E K", 11), ("5-9", 19)]:
        page.insert_text((30, y), text, fontsize=size)
        y += size + 14
    path = tmp_path / "003 - Tytul Karty.pdf"
    document.save(path)
    document.close()
    parsed = parse_card_pdf(path)
    assert parsed["number"] == "003" and parsed["title"] == "Tytul Karty"
    assert parsed["age_min"] == 5 and parsed["page_pt"] == [600, 800]
