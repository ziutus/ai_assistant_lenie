"""Pure chapter-boundary editing: no DB, LLM, or whitespace normalization on parse."""

import re

import pytest

from library.transcript_chapter_boundaries import (
    chapter_sentences, describe_sections, merge_chapter, move_boundary, parse_sections, render_sections, split_chapter,
)

TEXT = "Wstęp.\n\n## Pierwszy\n\nAla czyta. Żółw śpi!\n\nKot je?\n\n## Drugi\n\nPies biega. Pada…\n\nŚwieci słońce.\n"


def invariant(before, after):
    def content(text):
        return re.sub(r"\s", "", re.sub(r"^## [^\r\n]*", "", text, flags=re.M))
    assert content(before) == content(after)
    assert re.findall(r"^## [^\r\n]*", before, re.M) == re.findall(r"^## [^\r\n]*", after, re.M)


@pytest.mark.parametrize("text", ["", "  ", "Bez nagłówka.\n", TEXT, TEXT.replace("\n", "\r\n"),
                                      "# H1\n### H3\n\n## H2  \n\nTreść.  \n", "## Bez treści"])
def test_parse_render_identity(text):
    assert render_sections(parse_sections(text)) == text


@pytest.mark.parametrize("steps,counts", [(1, [4, 2]), (2, [5, 1]), (-1, [2, 4]), (-2, [1, 5])])
def test_moves_both_directions(steps, counts):
    changed = move_boundary(TEXT, 2, steps)
    invariant(TEXT, changed)
    descriptions = describe_sections(changed)
    assert [s["sentence_count"] for s in descriptions[1:]] == counts
    assert changed.startswith("Wstęp.\n\n## Pierwszy\n\n")
    assert "\n\n## Drugi\n\n" in changed
    if steps > 0:
        assert changed.index("Pies biega.") < changed.index("## Drugi")
    else:
        assert changed.index("Kot je?") > changed.index("## Drugi")


def test_description_and_preamble():
    sections = describe_sections(TEXT)
    assert sections[0] == {"position": 0, "title": "", "is_preamble": True, "sentence_count": 1,
                           "char_length": 8, "first_sentences": ["Wstęp."], "last_sentences": ["Wstęp."]}
    assert sections[1]["position"] == 1
    assert sections[1]["title"] == "Pierwszy"
    assert sections[1]["first_sentences"] == ["Ala czyta.", "Żółw śpi!"]
    assert sections[1]["last_sentences"] == ["Żółw śpi!", "Kot je?"]


@pytest.mark.parametrize("position,steps", [(1, 1), (0, 1), (3, 1), (2, 0), (2, 3), (2, -3),
                                          (2, 100), (2, -100), (True, 1), (2, True), (2, 1.5)])
def test_invalid_moves(position, steps):
    with pytest.raises(ValueError):
        move_boundary(TEXT, position, steps)


@pytest.mark.parametrize("text,steps", [("## A\nA.\n## B\nB. C.", -1),
                                       ("## A\nA. B.\n## B\nC.", 1),
                                       ("## A\n\n## B\nC. D.", 1),
                                       ("## A\nA. B.\n## B\n", -1)])
def test_neither_chapter_may_be_empty(text, steps):
    with pytest.raises(ValueError):
        move_boundary(text, 2, steps)


def test_last_boundary_and_untouched_other_sections():
    text = TEXT + "\n## Trzeci\n\nJeden. Dwa."
    changed = move_boundary(text, 3, -1)
    invariant(text, changed)
    assert parse_sections(changed)[:2] == parse_sections(text)[:2]
    assert describe_sections(changed)[-1]["first_sentences"] == ["Świeci słońce.", "Jeden."]


def test_polish_abbreviations_decimals_ellipsis():
    body = "Dr. Nowak zna m.in. prof. Kowalską, np. z ul. Łąkowej. Koszt to 3.14 zł… Naprawdę?! Tak... Koniec"
    text = "## A\n" + body + "\n\n## B\nRaz. Dwa."
    assert describe_sections(text)[0]["sentence_count"] == 5
    changed = move_boundary(text, 2, -4)
    invariant(text, changed)
    assert describe_sections(changed)[0]["last_sentences"] == [body.split(" Koszt")[0]]


def test_paragraphs_inside_moved_run_stay_intact():
    text = "## A\n\nA. B.\n\n## B\n\nC.\n\nD. E.\n\nF."
    changed = move_boundary(text, 2, 2)
    invariant(text, changed)
    assert "C.\n\nD.\n\n## B\n\nE.\n\nF." in changed
    back = move_boundary(changed, 2, -2)
    invariant(text, back)
    assert "C.\n\nD.\n\nE.\n\nF." in back


def test_h1_h3_are_content_not_chapters():
    assert [s["title"] for s in describe_sections("# H1\n### H3\n## A\nOne. Two.\n## B\nThree.")] == ["", "A", "B"]


def content(text):
    return re.sub(r"\s", "", "".join(section.body for section in parse_sections(text)))


@pytest.mark.parametrize("newline", ["\n", "\r\n"])
@pytest.mark.parametrize("position,sentence_index", [(1, 2), (1, 3), (2, 2), (2, 3)])
def test_split_merge_round_trip(newline, position, sentence_index):
    text = TEXT.replace("\n", newline)
    result = split_chapter(text, position, sentence_index, "  Żółć i źródła  ")
    assert content(result) == content(text)
    titles = [s["title"] for s in describe_sections(result) if s["position"]]
    assert titles == ["Pierwszy", "Drugi"][:position] + ["Żółć i źródła"] + ["Pierwszy", "Drugi"][position:]
    assert parse_sections(result)[0] == parse_sections(text)[0]
    assert newline * 2 + "## Żółć i źródła" + newline * 2 in result
    if newline == "\r\n":
        assert "\n" not in result.replace("\r\n", "")
    sections = describe_sections(result)
    assert sections[position]["sentence_count"] == sentence_index - 1
    assert sections[position + 1]["sentence_count"] == 4 - sentence_index
    merged = merge_chapter(result, position + 1)
    invariant(text, merged)
    assert parse_sections(merged)[0] == parse_sections(text)[0]
    # Normalized paragraph spacing is stable over repeated split/merge cycles.
    assert merge_chapter(split_chapter(merged, position, sentence_index, "Jeszcze raz"), position + 1) == merged


@pytest.mark.parametrize("position", [2, 3])
def test_merge_preserves_paragraphs_and_other_headings(position):
    text = TEXT + "\n## Trzeci\n\nNowy akapit.\n\nOstatni akapit."
    result = merge_chapter(text, position)
    assert content(text) == content(result)
    assert "Nowy akapit.\n\nOstatni akapit." in result
    titles = ["Pierwszy", "Drugi", "Trzeci"]
    assert [s["title"] for s in describe_sections(result)[1:]] == titles[:position - 1] + titles[position:]
    assert parse_sections(text)[0] == parse_sections(result)[0]


def test_merge_then_split_at_original_paragraph_is_identical():
    text = "Przedmowa.\r\n\r\n## A\r\n\r\nDr. Nowak czyta m.in. książkę.\r\n\r\n## B\r\n\r\nPada… Tak!"
    assert split_chapter(merge_chapter(text, 2), 1, 2, "B") == text


@pytest.mark.parametrize("position", [0, -1, 3, True, 1.0, "1"])
def test_split_invalid_position(position):
    with pytest.raises(ValueError):
        split_chapter(TEXT, position, 2, "Nowy")


@pytest.mark.parametrize("index", [0, 1, 4, -1, True, 2.0, "2"])
def test_split_invalid_sentence_index(index):
    with pytest.raises(ValueError):
        split_chapter(TEXT, 1, index, "Nowy")


@pytest.mark.parametrize("title", ["", "  ", "# Tytuł", "  ## Tytuł", "A\nB", "A\rB", "Tytuł\n", "A\u2028B",
                                  "a" * 201, None, True, 12])
def test_split_invalid_title(title):
    with pytest.raises(ValueError):
        split_chapter(TEXT, 1, 2, title)


def test_split_title_length_limit_and_single_sentence():
    assert describe_sections(split_chapter(TEXT, 1, 2, "ż" * 200))[2]["title"] == "ż" * 200
    with pytest.raises(ValueError):
        split_chapter("## A\nJedno zdanie.", 1, 2, "Nowy")
    with pytest.raises(ValueError):
        split_chapter("## A\n", 1, 2, "Nowy")


@pytest.mark.parametrize("position", [0, 1, -1, 3, True, 2.0, "2"])
def test_merge_invalid_position(position):
    with pytest.raises(ValueError):
        merge_chapter(TEXT, position)


def test_lazy_sentence_description_and_preamble():
    assert chapter_sentences(TEXT, 0) == {"position": 0, "title": "", "sentences": [{"index": 1, "text": "Wstęp."}]}
    assert chapter_sentences(TEXT, 2) == {"position": 2, "title": "Drugi", "sentences": [
        {"index": 1, "text": "Pies biega."}, {"index": 2, "text": "Pada…"}, {"index": 3, "text": "Świeci słońce."},
    ]}
    assert chapter_sentences("## Pusty", 1)["sentences"] == []


@pytest.mark.parametrize("text,position", [(TEXT, 3), (TEXT, True), (TEXT, -1), ("## A\nZdanie.", 0), ("", 0)])
def test_lazy_sentences_invalid_position(text, position):
    with pytest.raises(ValueError):
        chapter_sentences(text, position)
