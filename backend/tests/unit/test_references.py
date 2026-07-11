"""Unit tests for library/references.py — book footnote extraction."""

import pytest

pytest.importorskip("sqlalchemy")

from library.references import extract_footnotes, refresh_document_references  # noqa: E402


class TestExtractFootnotes:
    def test_superscript_marker_always_extracted(self):
        text = "Akapit tekstu.\n\n¹⁸ https://www.statista.com/statistics/973952/ (dostęp: 12.09.2024).\n\nDalszy tekst."
        clean, fns = extract_footnotes(text)
        assert len(fns) == 1
        assert fns[0]["marker"] == "18"
        assert fns[0]["url"] == "https://www.statista.com/statistics/973952/"
        assert "statista" not in clean
        assert "Akapit tekstu." in clean and "Dalszy tekst." in clean

    def test_superscript_with_bare_domain(self):
        """Domena bez www też jest URL-em ("¹¹ razna120lat.pl (dostęp: ...)")."""
        _, fns = extract_footnotes("¹³ polsa.gov.pl/wydarzenia/kosmiczne/ (dostęp: 04.04.2024).")
        assert fns[0]["marker"] == "13"
        assert fns[0]["url"] == "https://polsa.gov.pl/wydarzenia/kosmiczne/"

    def test_numbered_marker_with_url(self):
        _, fns = extract_footnotes("12 www.archiwum.nask.pl/pl/aktualnosci/5236.html (dostęp: 28.01.2024).")
        assert fns[0]["marker"] == "12"
        assert fns[0]["url"] == "https://www.archiwum.nask.pl/pl/aktualnosci/5236.html"

    def test_numbered_bibliographic_entry_with_year(self):
        _, fns = extract_footnotes("17 Zagraniczne inwestycje bezpośrednie w Polsce, Narodowy Bank Polski, Warszawa 2023.")
        assert fns[0]["marker"] == "17"
        assert fns[0]["url"] is None

    def test_short_biblio_without_year(self):
        """"29 Eurostat." — krótki wpis bibliograficzny bez roku i URL-a."""
        _, fns = extract_footnotes("29 Eurostat.")
        assert fns[0]["text"] == "Eurostat."

    def test_long_explanatory_footnote_with_year(self):
        text = ("2 Choćby z uwagi na sytuację w sektorze lotniczym. Spośród tysiąca samolotów "
                "latających do 2022 roku nad Rosją, blisko trzy czwarte to były maszyny leasingowane.")
        _, fns = extract_footnotes(text)
        assert len(fns) == 1

    def test_legal_citation(self):
        _, fns = extract_footnotes("2 Art. 173 Konstytucji Rzeczpospolitej Polskiej (Dz.U. 1997, nr 78, poz.483).")
        assert len(fns) == 1

    def test_narrative_paragraph_not_extracted(self):
        """Zwykły akapit ani nagłówek nie są przypisami."""
        text = ("# Rozdział\n\nW 2022 roku Polska zwiększyła wydatki na obronność. "
                "Wzrost był bezprecedensowy.\n\nKolejny akapit opowieści bez numeru.")
        clean, fns = extract_footnotes(text)
        assert fns == []
        assert clean == text

    def test_lowercase_continuation_after_number_not_extracted(self):
        """Linia "90 procent budżetu..." to narracja, nie przypis."""
        _, fns = extract_footnotes("90 procent budżetu przeznaczono na wojsko w 2023 roku.")
        assert fns == []

    def test_three_digit_number_not_a_marker(self):
        _, fns = extract_footnotes("500 Plus zmieniło politykę społeczną, Warszawa 2016.")
        assert fns == []

    def test_blank_runs_collapsed_after_removal(self):
        text = "Tekst.\n\n¹ Źródło, Warszawa 2020.\n\n² Inne źródło, Kraków 2021.\n\nDalej."
        clean, fns = extract_footnotes(text)
        assert len(fns) == 2
        assert "\n\n\n" not in clean

    def test_offsets_point_into_original_text(self):
        text = "Początek.\n\n¹ Źródło, Warszawa 2020.\n\nKoniec."
        _, fns = extract_footnotes(text)
        assert text[fns[0]["char_offset"]:].startswith("¹ Źródło")


class TestRefreshDocumentReferences:
    def test_no_footnotes_means_no_changes(self):
        from unittest.mock import MagicMock

        doc = MagicMock(id=9, text_md="# Tytuł\n\nZwykły tekst bez przypisów.")
        session = MagicMock()
        rows = refresh_document_references(session, doc)
        assert rows == []
        session.execute.assert_not_called()

    def test_extracts_assigns_chapters_and_updates_text(self):
        from unittest.mock import MagicMock

        text = ("# Rozdział pierwszy\n\nTreść pierwsza.\n\n¹ Źródło A, Warszawa 2020.\n\n"
                "# Rozdział drugi\n\nTreść druga.\n\n² Źródło B, Kraków 2021.\n")
        doc = MagicMock(id=9, text_md=text)
        session = MagicMock()

        rows = refresh_document_references(session, doc)

        assert [(r.marker, r.chapter_position) for r in rows] == [("1", 1), ("2", 2)]
        assert "Źródło A" not in doc.text_md
        assert "Treść pierwsza." in doc.text_md and "# Rozdział drugi" in doc.text_md
        session.execute.assert_called_once()  # DELETE poprzednich wierszy
        session.add_all.assert_called_once_with(rows)
