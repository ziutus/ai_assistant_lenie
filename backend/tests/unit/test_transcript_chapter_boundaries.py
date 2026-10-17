"""Pure chapter-boundary editing: no DB, LLM, or whitespace normalization on parse."""

import re

import pytest

from library.transcript_chapter_boundaries import describe_sections, move_boundary, parse_sections, render_sections

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
