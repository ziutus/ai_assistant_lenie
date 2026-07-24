"""Unit tests for imports.import_control_questions — pure parsing/tagging, no DB access."""

from imports.import_control_questions import _clean_header, _tags_for_header, load_questions_from_dir


class TestCleanHeader:
    def test_strips_hash_markers(self):
        assert _clean_header("## Jaką ma armię?") == "Jaką ma armię?"
        assert _clean_header("# Sekcja") == "Sekcja"


class TestTagsForHeader:
    def test_matches_known_needle(self):
        assert _tags_for_header("## Jaką ma armię w porównaniu do innych?") == "wojsko"

    def test_multiple_tags_sorted_and_deduplicated(self):
        assert _tags_for_header("## jaki jest stan finansów ?") == "finanse-publiczne,gospodarka"

    def test_no_match_returns_none(self):
        assert _tags_for_header("## Coś zupełnie innego") is None


class TestLoadQuestionsFromDir:
    def test_parses_all_md_files_skipping_preamble_and_non_md(self, tmp_path):
        (tmp_path / "a.md").write_text(
            "---\ntags:\n  - wiedza/geopolityka\n---\n"
            "## Jaką ma armię w porównaniu do innych?\nTreść.\n",
            encoding="utf-8",
        )
        (tmp_path / "b.md").write_text("## jaki jest stan finansów ?\nTreść 2.\n", encoding="utf-8")
        (tmp_path / "ignore.txt").write_text("nie powinno być zaimportowane", encoding="utf-8")

        rows = load_questions_from_dir(str(tmp_path))

        assert {r["source_file"] for r in rows} == {"a.md", "b.md"}
        armia = next(r for r in rows if r["source_file"] == "a.md")
        assert armia["section_header"] == "Jaką ma armię w porównaniu do innych?"
        assert armia["body"] == "Treść."
        assert armia["tags"] == "wojsko"
        assert armia["position"] == 0
        finanse = next(r for r in rows if r["source_file"] == "b.md")
        assert finanse["tags"] == "finanse-publiczne,gospodarka"

    def test_empty_dir_returns_no_rows(self, tmp_path):
        assert load_questions_from_dir(str(tmp_path)) == []

    def test_index_file_is_skipped(self, tmp_path):
        (tmp_path / "_index.md").write_text(
            "# Pytania kontrolne — indeks\n## Kiedy którego pliku używać?\ntreść nawigacyjna\n",
            encoding="utf-8",
        )

        assert load_questions_from_dir(str(tmp_path)) == []

    def test_headerless_file_falls_back_to_paragraphs(self, tmp_path):
        (tmp_path / "c.md").write_text(
            "czy porozumienie obsługuje potrzeby wewnętrzne ?\n"
            "przykładowe uzasadnienie w drugiej linii\n"
            "\n"
            "ile kosztuje demonstracja zbrojna?\n",
            encoding="utf-8",
        )

        rows = load_questions_from_dir(str(tmp_path))

        assert [r["section_header"] for r in rows] == [
            "czy porozumienie obsługuje potrzeby wewnętrzne ?",
            "ile kosztuje demonstracja zbrojna?",
        ]
        assert rows[0]["body"] == "przykładowe uzasadnienie w drugiej linii"
        assert rows[1]["body"] is None
        assert [r["position"] for r in rows] == [0, 1]
