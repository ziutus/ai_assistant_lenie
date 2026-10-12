"""Positioned-line regressions and cached integration checks for all three books."""

import csv
import json
import pathlib
import time
from collections import Counter
from types import SimpleNamespace

import pytest

from imports import project_cards_family_parse as cli
from library.project_card_family_parser import (
    parse_card_pdf,
    parse_lines,
    parse_time,
    read_lines,
    split_sections,
    valid_numbering,
)


def header(text, y, x=48):
    return " ".join(text.replace(" ", "")), 15, x, y


def top(duration="3 MIN"):
    return [
        header("KSIĄŻKA · WODA I", 69), header("CIECZE", 91), ("№ 001", 22.5, 690, 64),
        (duration, 13.5, 63, 119), ("Tajemnica Sz‐", 61.5, 48, 162), ("tuk", 61.5, 48, 225),
        ("Poznaj ciekawy świat.", 25.5, 48, 328), ("Opis doświadczenia.", 20.25, 48, 439),
    ]


@pytest.fixture
def experiment_lines():
    # Materials, stars and key tip occur after the footer in PDF reading order.
    return top() + [
        header("NAUKA O GĘSTOŚCI", 500), ("Sól zwiększa gęstość.", 20.25, 48, 540),
        header("CZEGO POTRZEBUJESZ", 600), header("SZTUCZKA Z PŁYWAJĄCYM JAJKIEM", 750),
        ("01", 24, 58, 791.4), ("Wlej wodę do", 19.5, 112, 790), ("szklanki.", 19.5, 112, 818),
        ("02", 24, 57, 861.4), ("Włóż jajko.", 19.5, 112, 860),
        header("WARIACJE EKSPERYMENTU", 910), header("NAJPIERW BEZPIECZEŃSTWO", 1010),
        ("Poproś dorosłego o pomoc.", 20.25, 48, 1050), ("001 · Książka", 16.5, 500, 1300),
        ("Szklanka", 19.5, 81, 640), ("◆", 16.5, 48, 640), ("z wodą", 19.5, 81, 668),
        ("Jajko", 19.5, 81, 706), ("◆", 16.5, 48, 706),
        ("Dodaj sól.", 19.5, 81, 950), ("✦", 16.5, 48, 952.8),
        header("KLUCZOWA WSKAZÓWKA", 1120, 81), ("Obserwuj uważnie.", 21, 81, 1160), ("“", 135, 673, 1080),
    ]


@pytest.fixture
def craft_lines():
    return top("1 GODZ") + [
        header("POTRZEBNE", 500), header("MATERIAŁY", 521),
        header("PIERWSZE KROKI", 700), ("01", 24, 58, 741.4), ("Zanurz gąbkę.", 19.5, 112, 740),
        ("02", 24, 57, 791.4), ("Odbij na papierze.", 19.5, 112, 790),
        header("UŁATWIAMY I UTRZYMUJEMY CZYSTOŚĆ", 860), ("001 · Książka", 16.5, 500, 1200),
        ("Duża gąbka", 19.5, 81, 560), ("◆", 16.5, 48, 560),
        ("Papier", 19.5, 81, 610), ("◆", 16.5, 48, 610),
        ("Dorosły przygotowuje farby.", 19.5, 81, 900), ("✦", 16.5, 48, 902.8),
    ]


@pytest.fixture
def puzzle_lines():
    return top() + [
        header("ZAGADKA", 500), ("Ile to jest dwa i dwa?", 20.25, 48, 540),
        header("ANALIZA", 610), ("Dodaj obie liczby.", 20.25, 48, 650),
        header("ROZWIĄZANIE", 710), header("TAJEMNICY", 731),
        ("01", 24, 58, 781.4), ("Zacznij od dwóch.", 19.5, 112, 780),
        ("02", 24, 57, 831.4), ("Dodaj dwa.", 19.5, 112, 830),
        header("ODPOWIEDŹ", 900), ("Cztery.", 20.25, 48, 940),
        header("KLUCZOWA RADA", 1010), ("Licz powoli.", 21, 81, 1050),
    ]


def test_experiment_visual_order_and_complete_record(experiment_lines):
    card = parse_lines(experiment_lines, series="Nauka", kind="experiment", age_min=6, age_max=12,
                       source_file="science.pdf", source_page=3)
    assert card["title"] == "Tajemnica Sztuk"
    assert card["chapter"] == "WODAICIECZE"
    assert card["tagline"] == "Poznaj ciekawy świat."
    assert card["description"] == "Opis doświadczenia."
    assert card["materials"] == [{"qty": "", "name": "Szklanka z wodą"}, {"qty": "", "name": "Jajko"}]
    assert card["steps"] == ["Wlej wodę do szklanki.", "Włóż jajko."]
    assert card["variants"] == ["Dodaj sól."]
    assert card["safety"] == "Poproś dorosłego o pomoc."
    assert [s["role"] for s in card["sections"]] == ["explanation", "key_tip"]
    assert card["needs_adult"] and card["age_source"] == "cover"
    assert not card["flags"]
    assert set(card) == set("number series kind chapter title tagline description time_raw time_min time_max "
                            "age_min age_max age_source needs_adult materials tools steps variants safety sections "
                            "flags source_file source_page".split())
    # Input order must not affect the attribution.
    assert parse_lines(list(reversed(experiment_lines)), series="Nauka", kind="experiment")["steps"] == card["steps"]


def test_craft_wrapped_header_and_adult_tip(craft_lines):
    card = parse_lines(craft_lines, series="Rękodzieło", kind="craft", age_min=0)
    assert card["time_min"] == card["time_max"] == 60
    assert len(card["materials"]) == len(card["steps"]) == 2
    assert card["sections"][0]["content"] == ["Dorosły przygotowuje farby."]
    assert card["sections"][0]["role"] == "tip"
    assert card["needs_adult"] and card["age_source"] == "cover"
    assert card["age_min"] == 0 and card["age_max"] is None
    assert not card["flags"]


def test_puzzle_numbered_solutions_are_hidden(puzzle_lines):
    card = parse_lines(puzzle_lines, series="Logika", kind="puzzle")
    assert card["steps"] == card["materials"] == []
    assert card["age_source"] is None
    assert [(s["role"], s["hidden"]) for s in card["sections"]] == [
        ("puzzle", False), ("analysis", False), ("solution", True), ("answer", True), ("key_tip", False),
    ]
    assert card["sections"][2]["format"] == "steps"
    assert card["sections"][2]["content"] == ["Zacznij od dwóch.", "Dodaj dwa."]
    assert not card["flags"]


def test_inline_answer_and_two_digit_domino_values():
    lines = top() + [header("WYZWANIE", 500), ("◆", 16.5, 48, 540), ("31", 19.5, 81, 540),
                     ("◆", 16.5, 48, 580), ("14", 19.5, 81, 580),
                     ("◆", 16.5, 48, 620), ("Ile? (Odpowiedź: 2)", 19.5, 81, 620)]
    card = parse_lines(lines, series="Logika", kind="puzzle")
    assert card["sections"][0]["content"] == ["31", "14", "Ile?"]
    assert card["sections"][1]["hidden"]
    assert card["sections"][1]["content"] == ["(Odpowiedź: 2)"]


def test_unknown_and_missing_flags_do_not_invent_content():
    card = parse_lines(top("KIEDYŚ") + [header("NIEZNANY NAGŁÓWEK", 500)], series="Test", kind="craft")
    assert set(card["flags"]) == {"unmapped_section:NIEZNANYNAGŁÓWEK", "empty_section:other", "time_unparsed",
                                  "missing:materials", "missing:steps", "few_steps"}
    assert card["steps"] == card["materials"] == []
    assert card["sections"][0]["role"] == "other"


@pytest.mark.parametrize("raw,expected", [("3 MIN", (3, 3)), ("1 GODZ", (60, 60)),
                                         ("10-15 MIN", (10, 15)), ("1–2 GODZ", (60, 120)),
                                         ("3 MINUT Y", (3, 3)), ("?", (None, None))])
def test_time(raw, expected):
    assert parse_time(raw) == expected


def test_reader_ignores_quote_and_oversized_space_bbox():
    def span(text, size, y):
        return dict(text=text, size=size, origin=(81, 600), bbox=(81, y, 700, 620))

    page = SimpleNamespace(get_text=lambda _: {"blocks": [{"lines": [{"spans": [
        span("Waga to ", 21, 580), span("siła.", 21, 580), span(" ", 135, 490), span("“", 135, 490),
    ]}]}]})
    assert read_lines(page) == [("Waga to siła.", 21, 81, 580)]


def test_solution_table_keeps_analysis_visible():
    lines = top() + [header("ANALIZA PRZYKŁADU", 500), ("ZADANIE", 15, 48, 540),
                     ("ROZWIĄZANIE", 15, 630, 540), ("Dwa i dwa?", 18, 48, 580), ("4", 18, 630, 580)]
    card = parse_lines(lines, series="Test", kind="puzzle")
    assert card["sections"][0]["role"] == "analysis" and not card["sections"][0]["hidden"]
    assert card["sections"][1]["content"] == ["4"] and card["sections"][1]["hidden"]


@pytest.mark.parametrize("numbers,valid", [([], False), ([1, 2], True), ([1, 3], False),
                                          ([1, 2, 2], False), ([0, 1], False), ([2, 1], True)])
def test_numbering(numbers, valid):
    assert valid_numbering([{"number": f"{n:03d}"} for n in numbers]) is valid


@pytest.mark.parametrize("numbers,code", [([1, 2], 0), ([1, 3], 1), ([1, 1], 1)])
def test_cli_outputs_and_exit_status(tmp_path, monkeypatch, capsys, experiment_lines, numbers, code):
    card = parse_lines(experiment_lines, series="Nauka", kind="experiment")
    cards = [dict(card, number=f"{number:03d}") for number in numbers]
    pdf = tmp_path / "book.pdf"
    pdf.touch()

    def parse(*args, **kwargs):
        kwargs["inventory"][("NAUKAOGĘSTOŚCI", "explanation")] += len(cards)
        return cards

    monkeypatch.setattr(cli, "parse_card_pdf", parse)
    out = tmp_path / "out"
    assert cli.main([str(pdf), "--series", "Nauka", "--kind", "experiment", "--out-dir", str(out)]) == code
    assert json.loads((out / "cards.json").read_text(encoding="utf-8")) == cards
    assert (out / "review.csv").read_bytes().startswith(b"\xef\xbb\xbf")
    with (out / "review.csv").open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.reader(handle, delimiter=";"))
    assert rows[0] == ["nr", "tytuł", "rozdział", "czas", "kroki", "materiały", "sekcje", "dorosły", "flagi"]
    assert len(rows) == len(cards) + 1
    assert "NAUKAOGĘSTOŚCI;explanation;2" in capsys.readouterr().out


PDF_DIR = pathlib.Path(__file__).resolve().parents[2] / "tmp/project_card_families/pdfs"
BOOKS = [
    ("pl_200-Home-Science-Experiments.pdf", "experiment", "Domowe Eksperymenty Naukowe", 200, None, None),
    ("pl_150-Projects-for-Little-Ones.pdf", "craft", "Bezpieczne i Proste Rękodzieło", 150, 0, None),
    ("pl_150-Logic-Brain-Teaser-Challenges.pdf", "puzzle", "Laboratorium Logiki", 150, 6, 12),
]


@pytest.fixture(scope="module", params=[pytest.param(book, id=book[1], marks=pytest.mark.skipif(
    not (PDF_DIR / book[0]).is_file(), reason="Local card-book PDF is absent")) for book in BOOKS])
def book(request):
    filename, kind, series, count, age_min, age_max = request.param
    pytest.importorskip("fitz")
    inventory = Counter()
    started = time.perf_counter()
    cards = parse_card_pdf(PDF_DIR / filename, series=series, kind=kind, age_min=age_min,
                           age_max=age_max, inventory=inventory)
    elapsed = time.perf_counter() - started
    print(f"\n{kind}: {len(cards)} cards in {elapsed:.3f}s; flags={Counter(f for c in cards for f in c['flags'])}")
    return kind, count, cards, inventory


def test_real_book_integrity(book):
    kind, count, cards, inventory = book
    assert len(cards) == count
    assert [card["number"] for card in cards] == [f"{n:03d}" for n in range(1, count + 1)]
    assert all(card["title"] and card["description"] and card["chapter"] for card in cards)
    assert all(card["time_min"] is not None for card in cards)
    assert sum(any(f.startswith("unmapped_section:") for f in c["flags"]) for c in cards) <= count * .05
    assert not [(header, role) for header, role in inventory if role == "other"]
    assert inventory[("KLUCZOWARADA" if kind == "puzzle" else "KLUCZOWAWSKAZÓWKA", "key_tip")] == count


def test_real_source_gap_invariants(book):
    kind, count, cards, _ = book
    if kind == "puzzle":
        for card in cards:
            assert card["steps"] == card["materials"] == []
            assert any(s["role"] in {"solution", "answer"} and s["hidden"] for s in card["sections"])
            assert all(s["hidden"] == (s["role"] in {"solution", "answer"}) for s in card["sections"])
        return
    for card in cards:
        assert (not card["materials"]) == ("missing:materials" in card["flags"])
        assert (not card["steps"]) == ("missing:steps" in card["flags"])
        assert (len(card["steps"]) < 2) == ("few_steps" in card["flags"])
    # Observed source gaps: experiments 109 materials / 15 numbered steps;
    # crafts 36 materials / 17 numbered steps. Deliberately broad sanity bands:
    # source-preserving extraction must not invent lists to satisfy completeness.
    materials_low, materials_high = (70, 145) if kind == "experiment" else (15, 65)
    assert materials_low <= sum(not c["materials"] for c in cards) <= materials_high
    assert 5 <= sum(not c["steps"] for c in cards) <= 35
    assert all(not s["hidden"] for c in cards for s in c["sections"])


def test_real_importer_accepts_every_record(book):
    from library.project_cards import normalize_import_card

    for card in book[2]:
        normalized = normalize_import_card(card)
        assert normalized["number"] == int(card["number"])
        assert normalized["kind"] == card["kind"]


def test_real_content_regressions(book):
    kind, _, cards, _ = book
    first = cards[0]
    if kind == "experiment":
        assert first["chapter"] == "Woda i ciecze"
        assert first["materials"] == []  # Card 001 really has no materials section.
        assert cards[1]["materials"][0]["name"] == "Czerwona kapusta (kilka liści)"
        assert len(cards[1]["steps"]) == 7  # Two procedures; numbered materials are not steps.
        assert cards[93]["sections"][-1]["content"] == "Waga to siła, z jaką grawitacja przyciąga masę obiektu."
    elif kind == "craft":
        assert first["chapter"] == "Malowanie i stemplowanie bez pędzla"
        assert len(first["materials"]) == 5 and len(first["steps"]) == 4
        assert first["materials"][0]["name"].startswith("Gąbki kuchenne")
    else:
        assert first["title"] == "Tajemnica Trzynastu Sztuk"
        dominoes = next(s for s in cards[80]["sections"] if s["title"] == "Twoje kostki domino")
        assert dominoes["content"] == ["31", "14", "85", "58", "42", "28"]
    assert all(not any("K L U C Z O W A" in str(s["content"]) for s in c["sections"]) for c in cards)


def test_short_headers_are_not_swallowed():
    assert split_sections(top() + [header("CEL", 500), ("Cel zadania.", 20, 48, 550)])[1][0][0] == "CEL"


def test_readable_title_restores_sentence_case_and_joins_wrapped_headers():
    from library.project_card_family_parser import readable_title

    titles = {"DLACZEGOTODZIAŁA:FIZYKAWAKCJI": "DLACZEGO TO DZIAŁA: FIZYKA W AKCJI",
              "NAUKAO": "NAUKA O", "GĘSTOŚCI": "GĘSTOŚCI"}
    assert readable_title("DLACZEGOTODZIAŁA:FIZYKAWAKCJI", titles) == "Dlaczego to działa: fizyka w akcji"
    assert readable_title("NAUKAOGĘSTOŚCI", titles) == "Nauka o gęstości"
    assert readable_title("NIEZNANY", titles) is None and readable_title("X", None) is None


class _RawPage:
    """Minimal stand-in for a PyMuPDF page exposing rawdict chars with bboxes."""

    def __init__(self, lines):
        self._lines = lines

    def get_text(self, mode):
        assert mode == "rawdict"
        return {"blocks": [{"lines": [{"spans": [{"chars": line}]} for line in self._lines]}]}


def _letter_spaced(text, *, start=30.0, tracking=3.5, word_gap=10.0, width=7.0):
    chars, x = [], start
    for letter in text:
        if letter == " ":
            x += word_gap - tracking
            continue
        chars.append({"c": letter, "bbox": (x, 0, x + width, 10)})
        x += width + tracking
    return chars


def test_readable_headers_recovers_word_breaks_from_glyph_gaps():
    from library.project_card_family_parser import readable_headers

    page = _RawPage([
        _letter_spaced("CZEGO POTRZEBUJESZ"),
        _letter_spaced("DLACZEGO TO DZIAŁA"),
        [{"c": letter, "bbox": (i * 6.0, 0, i * 6.0 + 6.0, 10)} for i, letter in enumerate("NORMAL TEXT HERE")],
        _letter_spaced("Mixed Case Header"),
    ])
    assert readable_headers(page) == {"CZEGOPOTRZEBUJESZ": "CZEGO POTRZEBUJESZ",
                                      "DLACZEGOTODZIAŁA": "DLACZEGO TO DZIAŁA"}
