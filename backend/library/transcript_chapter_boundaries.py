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


def describe_sections(text: str) -> list[dict]:
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
