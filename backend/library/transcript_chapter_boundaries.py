"""Lossless H2 transcript sections and sentence-based chapter boundary edits."""

import re
from dataclasses import dataclass

_HEADING = re.compile(r"^## [^\r\n]*", re.MULTILINE)
_END = re.compile(r"[.!?…]+(?=\s|$)")
_ABBREVIATION = re.compile(
    r"(?:\b(?:np|itp|itd|tj|tzn|dr|prof|mgr|inż|ul|al|nr|pkt|ust|art|godz|ok|r|im)"
    r"|\bm\.in|\btzw)\.$", re.IGNORECASE,
)


@dataclass(frozen=True)
class Section:
    """Raw heading (empty for preamble) and body, including all whitespace."""

    heading: str
    body: str


def parse_sections(text: str) -> list[Section]:
    matches = list(_HEADING.finditer(text))
    sections = []
    first = matches[0].start() if matches else len(text)
    if first or not matches:
        sections.append(Section("", text[:first]))
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        sections.append(Section(match.group(), text[match.end():end]))
    return sections


def render_sections(sections: list[Section]) -> str:
    return "".join(section.heading + section.body for section in sections)


def _sentence_spans(body: str) -> list[tuple[int, int]]:
    """Offsets retain paragraphs; decimals and dotted abbreviations stay whole."""
    spans = []
    start = 0
    for match in _END.finditer(body):
        if match.group() == "." and _ABBREVIATION.search(body[:match.end()]):
            continue
        if body[start:match.end()].strip():
            spans.append((start, match.end()))
        start = match.end()
    if body[start:].strip():
        spans.append((start, len(body)))
    return spans


def describe_sections(text: str, *, with_sentences: bool = False) -> list[dict]:
    """Describe H2 chapters, with position 0 reserved for an optional preamble."""
    result = []
    position = 0
    for section in parse_sections(text):
        if section.heading:
            position += 1
        elif not section.body:
            continue
        sentences = [section.body[start:end].strip() for start, end in _sentence_spans(section.body)]
        result.append({
            "position": position,
            "title": section.heading[3:].strip() if section.heading else "",
            "is_preamble": not bool(section.heading),
            "sentence_count": len(sentences),
            "char_length": len(section.body),
            "first_sentences": sentences[:2],
            "last_sentences": sentences[-2:],
            **({"sentences": [{"index": index, "text": sentence} for index, sentence in enumerate(sentences, 1)]}
               if with_sentences else {}),
        })
    return result


def _content(sections: list[Section]) -> str:
    return re.sub(r"\s", "", "".join(section.body for section in sections))


def move_boundary(text: str, position: int, sentences: int) -> str:
    """Move one H2 heading, retaining transcript order and internal paragraphs."""
    sections = parse_sections(text)
    chapters = [index for index, section in enumerate(sections) if section.heading]
    if type(position) is not int or not 2 <= position <= len(chapters):
        raise ValueError("Wybierz granicę od drugiego do ostatniego rozdziału.")
    if type(sentences) is not int or sentences == 0:
        raise ValueError("Liczba zdań musi być niezerową liczbą całkowitą.")
    index = chapters[position - 1]
    previous, current = sections[index - 1:index + 1]
    left = _sentence_spans(previous.body)
    right = _sentence_spans(current.body)
    if not left or not right or (sentences > 0 and sentences >= len(right)) or (
        sentences < 0 and -sentences >= len(left)
    ):
        raise ValueError("Przesunięcie nie może pozostawić rozdziału bez zdań.")

    # Keep a paragraph at the old heading, without accumulating blank lines on repeated edits.
    newline = "\r\n" if "\r\n" in current.body else "\n"
    prefix = previous.body.rstrip() + newline * 2
    body = current.body.lstrip()
    merged = prefix + body
    boundary = (len(prefix) + _sentence_spans(body)[sentences - 1][1] if sentences > 0
                else left[len(left) + sentences - 1][1])
    updated = sections.copy()
    updated[index - 1] = Section(previous.heading, merged[:boundary].rstrip() + newline * 2)
    updated[index] = Section(current.heading, newline * 2 + merged[boundary:].lstrip())
    result = render_sections(updated)
    reparsed = parse_sections(result)
    assert _content(sections) == _content(reparsed), "Transcript content changed"
    assert [s.heading for s in sections if s.heading] == [s.heading for s in reparsed if s.heading]
    return result


def _section_index(sections: list[Section], position: int, *, allow_preamble: bool = False) -> int:
    chapters = [index for index, section in enumerate(sections) if section.heading]
    if type(position) is int:
        if allow_preamble and position == 0 and sections and not sections[0].heading and sections[0].body:
            return 0
        if 1 <= position <= len(chapters):
            return chapters[position - 1]
    raise ValueError("Nie ma rozdziału o podanym numerze.")


def chapter_sentences(text: str, position: int) -> dict:
    """Return sentence text for one chapter only (position 0 denotes the preamble)."""
    sections = parse_sections(text)
    section = sections[_section_index(sections, position, allow_preamble=True)]
    return {
        "position": position,
        "title": section.heading[3:].strip() if section.heading else "",
        "sentences": [
            {"index": index, "text": section.body[start:end].strip()}
            for index, (start, end) in enumerate(_sentence_spans(section.body), 1)
        ],
    }


def _render_edit(original: list[Section], updated: list[Section]) -> str:
    result = render_sections(updated)
    reparsed = parse_sections(result)
    assert _content(original) == _content(reparsed), "Transcript content changed"
    assert [s.heading for s in updated if s.heading] == [s.heading for s in reparsed if s.heading]
    return result


def split_chapter(text: str, position: int, sentence_index: int, title: str) -> str:
    """Insert an H2 before a sentence, without rewriting either half."""
    sections = parse_sections(text)
    index = _section_index(sections, position)
    section = sections[index]
    spans = _sentence_spans(section.body)
    if type(sentence_index) is not int or not 2 <= sentence_index <= len(spans):
        raise ValueError("Nowy rozdział musi zaczynać się od drugiego lub późniejszego zdania.")
    if not isinstance(title, str) or re.search(r"[\r\n\v\f\x85\u2028\u2029]", title):
        raise ValueError("Tytuł musi być tekstem w jednym wierszu.")
    title = title.strip()
    if not title or title.startswith("#") or len(title) > 200:
        raise ValueError("Podaj tytuł o długości 1–200 znaków, bez znaku # na początku.")
    newline = "\r\n" if "\r\n" in section.body else "\n"
    boundary = spans[sentence_index - 2][1]
    updated = sections.copy()
    updated[index:index + 1] = [
        Section(section.heading, section.body[:boundary].rstrip() + newline * 2),
        Section("## " + title, newline * 2 + section.body[boundary:].lstrip()),
    ]
    assert [s.heading for s in updated if s.heading] == (
        [s.heading for s in sections if s.heading][:position] + ["## " + title]
        + [s.heading for s in sections if s.heading][position:]
    )
    return _render_edit(sections, updated)


def merge_chapter(text: str, position: int) -> str:
    """Remove one H2 and join its body to the preceding chapter as a paragraph."""
    sections = parse_sections(text)
    index = _section_index(sections, position)
    if position < 2:
        raise ValueError("Pierwszego rozdziału nie można scalić z poprzednim.")
    previous, current = sections[index - 1:index + 1]
    newline = "\r\n" if "\r\n" in current.body or "\r\n" in previous.body else "\n"
    updated = sections.copy()
    updated[index - 1:index + 1] = [
        Section(previous.heading, previous.body.rstrip() + newline * 2 + current.body.lstrip()),
    ]
    headings = [s.heading for s in sections if s.heading]
    assert [s.heading for s in updated if s.heading] == headings[:position - 1] + headings[position:]
    return _render_edit(sections, updated)
