"""Unit tests for library.text_functions.split_markdown_into_chunks."""

from library.text_functions import split_markdown_into_chunks


class TestSplitMarkdownIntoChunks:
    def test_empty_text_returns_empty_list(self):
        assert split_markdown_into_chunks("", 1000) == []
        assert split_markdown_into_chunks("   \n\n  ", 1000) == []

    def test_short_text_single_chunk(self):
        text = "# Tytuł\n\nKrótki akapit."
        assert split_markdown_into_chunks(text, 1000) == [text]

    def test_splits_at_headers_when_over_limit(self):
        sec1 = "# Rozdział 1\n\n" + "a" * 60
        sec2 = "# Rozdział 2\n\n" + "b" * 60
        chunks = split_markdown_into_chunks(f"{sec1}\n\n{sec2}", 100)
        assert chunks == [sec1, sec2]

    def test_packs_small_sections_together(self):
        sec1 = "## A\n\nkrótki"
        sec2 = "## B\n\nkrótki"
        sec3 = "## C\n\nkrótki"
        chunks = split_markdown_into_chunks(f"{sec1}\n\n{sec2}\n\n{sec3}", 1000)
        assert len(chunks) == 1
        assert sec1 in chunks[0] and sec3 in chunks[0]

    def test_header_starts_new_chunk_not_middle(self):
        """A header never lands at the end of a chunk without its content."""
        sec1 = "# Pierwszy\n\n" + "x" * 80
        sec2 = "# Drugi\n\n" + "y" * 80
        chunks = split_markdown_into_chunks(f"{sec1}\n\n{sec2}", 120)
        assert chunks[0].startswith("# Pierwszy")
        assert chunks[1].startswith("# Drugi")

    def test_preamble_before_first_header_is_kept(self):
        text = "Wstęp bez nagłówka.\n\n# Rozdział\n\nTreść."
        chunks = split_markdown_into_chunks(text, 1000)
        assert len(chunks) == 1
        assert chunks[0].startswith("Wstęp")

    def test_oversized_section_split_by_paragraphs(self):
        paras = "\n\n".join("p" * 50 for _ in range(5))
        text = f"# Duży rozdział\n\n{paras}"
        chunks = split_markdown_into_chunks(text, 120)
        assert len(chunks) > 1
        assert all(len(c) <= 120 for c in chunks)

    def test_no_headers_falls_back_to_paragraphs(self):
        text = "\n\n".join(f"Akapit {i} " + "z" * 40 for i in range(4))
        chunks = split_markdown_into_chunks(text, 100)
        assert len(chunks) > 1
        assert "".join(chunks).count("Akapit") == 4

    def test_all_header_levels_recognized(self):
        text = "###### Głęboki\n\n" + "a" * 60 + "\n\n## Płytki\n\n" + "b" * 60
        chunks = split_markdown_into_chunks(text, 80)
        assert len(chunks) == 2
        assert chunks[1].startswith("## Płytki")

    def test_hash_inside_line_is_not_a_header(self):
        """'#' not at line start (e.g. C# or anchors) must not create a boundary."""
        text = "Język C# oraz F# to platforma .NET. " * 3
        chunks = split_markdown_into_chunks(text, 1000)
        assert len(chunks) == 1


class TestTailMerge:
    def test_small_tail_merged_into_previous(self):
        """A document just over the limit must not leave an orphan tail chunk."""
        # 3 paragraphs: 480+480+60 = ~1024 chars with a 1000 limit
        text = "\n\n".join(["a" * 480, "b" * 480, "c" * 60])
        chunks = split_markdown_into_chunks(text, 1000)
        assert len(chunks) == 1
        assert chunks[0].endswith("c" * 60)

    def test_large_tail_stays_separate(self):
        # tail of 400 chars (40% of limit) must remain its own chunk
        text = "\n\n".join(["a" * 480, "b" * 480, "c" * 400])
        chunks = split_markdown_into_chunks(text, 1000)
        assert len(chunks) == 2
        assert chunks[1] == "c" * 400

    def test_sentence_splitter_merges_small_tail(self):
        from library.text_functions import split_text_into_sentence_chunks
        sentences = ("Zdanie ma tutaj dokladnie piecdziesiat znakow tu. " * 20).strip()
        # ~1000 chars of sentences + one short trailing sentence, limit 1000
        text = sentences + " Kropka."
        chunks = split_text_into_sentence_chunks(text, 1000)
        assert len(chunks) == 1 or len(chunks[-1]) >= 150
