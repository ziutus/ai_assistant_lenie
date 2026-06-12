"""Unit tests for imports.control_questions — markdown section parsing and tag filtering.

Pure-function tests, no file system or DB access.
"""

from imports.control_questions import TAG_TO_HEADERS, parse_sections, sections_for_tags

SAMPLE = """Wstęp bez nagłówka.

## Jaką ma armię ten kraj?

Pytania o wojsko.

## Jaki model ekonomiczny dominuje w tym kraju?

Pytania o gospodarkę.

# Sekcja H1

Treść H1.

### Podsekcja H3 — nie jest osobną sekcją

## Rola religii w państwie

Pytania o religię.
"""


class TestParseSections:
    def test_splits_on_h1_and_h2(self):
        sections = parse_sections(SAMPLE)
        headers = [h for h, _ in sections]
        assert "## Jaką ma armię ten kraj?" in headers
        assert "## Jaki model ekonomiczny dominuje w tym kraju?" in headers
        assert "# Sekcja H1" in headers
        assert "## Rola religii w państwie" in headers

    def test_preamble_kept_as_headerless_section(self):
        sections = parse_sections(SAMPLE)
        assert sections[0][0] == ""
        assert "Wstęp bez nagłówka." in sections[0][1]

    def test_h3_stays_inside_parent_section(self):
        sections = parse_sections(SAMPLE)
        h1_body = next(body for header, body in sections if header == "# Sekcja H1")
        assert "### Podsekcja H3" in h1_body

    def test_body_attached_to_its_header(self):
        sections = parse_sections(SAMPLE)
        armia_body = next(body for header, body in sections if "armię" in header)
        assert armia_body == "Pytania o wojsko."

    def test_empty_input(self):
        assert parse_sections("") == []


class TestSectionsForTags:
    def test_matches_by_tag(self):
        sections = parse_sections(SAMPLE)
        matched = sections_for_tags(sections, ["wojsko"])
        assert len(matched) == 1
        assert "armię" in matched[0][0]

    def test_match_is_case_insensitive(self):
        sections = [("## JAKĄ MA ARMIĘ?", "treść")]
        matched = sections_for_tags(sections, ["wojsko"])
        assert len(matched) == 1

    def test_multiple_tags_deduplicate_sections(self):
        # "stan finansów" jest i w 'gospodarka', i w 'finanse-publiczne'
        sections = [("## Stan finansów państwa", "treść")]
        matched = sections_for_tags(sections, ["gospodarka", "finanse-publiczne"])
        assert len(matched) == 1

    def test_unknown_tag_matches_nothing(self):
        sections = parse_sections(SAMPLE)
        assert sections_for_tags(sections, ["nie-ma-takiego-taga"]) == []

    def test_all_tag_needles_are_lowercase(self):
        # Dopasowanie robi header.lower() — frazy muszą być małymi literami
        for tag, needles in TAG_TO_HEADERS.items():
            for needle in needles:
                assert needle == needle.lower(), f"tag {tag}: '{needle}' nie jest lowercase"
