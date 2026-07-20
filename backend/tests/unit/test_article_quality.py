"""Unit tests for library.article_quality — photo-caption detection and
deterministic quality ("staranność") scoring.

Pure-function tests, no DB/LLM/network (compute_quality tested with model=None).
"""

from types import SimpleNamespace
from unittest.mock import MagicMock

from library.article_quality import (
    compute_quality,
    count_photo_captions,
    extract_press_bibliography,
    is_clickbait_title,
    is_photo_caption_line,
    is_references_section,
    photo_caption_candidates,
    remove_photo_caption_lines,
)

PRESS_BIBLIOGRAPHY = "\n".join([
    "**Źródła:**",
    "",
    '* The Guardian — "Papua New Guinea killings: what’s behind the outbreak in tribal fighting?"',
    '* Radio New Zealand — "**Brutal killings of two women in Papua New Guinea spark outrage"**',
    "* Time.com — \"A Fight Between Rivaling Tribes in Papua New Guinea Has Led to a Massacre\"",
    "* MSZ",
    "* World Population Review",
])

LONG_PARAGRAPH = (
    "To jest długi akapit właściwej treści artykułu, w którym autor rzetelnie "
    "opisuje temat, cytuje ekspertów i przywołuje dane z oficjalnych raportów."
)


class _Doc:
    def __init__(self, author=None, title=None, url=None, id=None):
        self.byline = author
        self.title = title
        self.url = url
        self.id = id


def _fake_session(rows):
    """MagicMock session whose scalars(select(...)).all() returns the given rows."""
    session = MagicMock()
    session.scalars.return_value.all.return_value = rows
    return session


class TestPhotoCaptionDetection:
    def test_zdjecie_ilustracyjne_with_stock_credit(self):
        assert is_photo_caption_line("zdjęcie ilustracyjne, Dmytro Buiansky / shutterstock")

    def test_fot_prefix(self):
        assert is_photo_caption_line("Fot. Jan Kowalski / PAP")

    def test_agency_only_line(self):
        assert is_photo_caption_line("Getty Images")

    def test_caption_next_to_img_marker(self):
        assert is_photo_caption_line("[img3] Zdjęcie ilustracyjne / East News")

    def test_zrodlo_zdjecia(self):
        assert is_photo_caption_line("Źródło zdjęcia: Unsplash")

    def test_long_caption_ending_with_zdjecie_ilustracyjne(self):
        line = (
            "Chiński rząd nakazał zaprzestanie produkcji aut ośmiu firmom. "
            "Niektóre były pionierami chińskiej motoryzacji (zdjęcie ilustracyjne)"
        )
        assert is_photo_caption_line(line)

    def test_long_paragraph_mentioning_photo_is_not_caption(self):
        text = (
            "Na opublikowanym przez agencję zdjęciu widać skutki wybuchu, a fotograf "
            "Reuters relacjonował wydarzenia z centrum miasta przez kilka kolejnych dni, "
            "dokumentując życie mieszkańców po ostrzale."
        )
        assert not is_photo_caption_line(text)

    def test_regular_sentence_is_not_caption(self):
        assert not is_photo_caption_line(LONG_PARAGRAPH[:100])

    def test_empty_line(self):
        assert not is_photo_caption_line("")

    def test_count_in_text(self):
        text = "\n".join([
            LONG_PARAGRAPH,
            "zdjęcie ilustracyjne, Dmytro Buiansky / shutterstock",
            LONG_PARAGRAPH,
            "Fot. Adam Nowak / East News",
        ])
        assert count_photo_captions(text) == 2

    def test_count_empty_text(self):
        assert count_photo_captions("") == 0

    def test_candidates_preserve_license_and_public_domain_evidence(self):
        text = "\n".join([
            LONG_PARAGRAPH,
            "Makieta obozu (fot. Drozdp), licencja CC BY-SA 4.0",
            "Salomon Morel, 1948 r., domena publiczna",
            "Źródło Archiwum FUF / archiwum prywatne",
        ])
        candidates = photo_caption_candidates(text)
        assert [item["line_index"] for item in candidates] == [1, 2, 3]
        assert [item["category"] for item in candidates] == [
            "creative_commons", "public_domain", "own_or_private_archive",
        ]

    def test_embedding_filter_removes_caption_without_mutating_source(self):
        source = f"{LONG_PARAGRAPH}\nFot. Jan Kowalski / PAP\n{LONG_PARAGRAPH}"
        filtered = remove_photo_caption_lines(source)
        assert "Fot. Jan Kowalski" not in filtered
        assert filtered.count(LONG_PARAGRAPH) == 2
        assert "Fot. Jan Kowalski" in source

    def test_image_marker_makes_following_description_a_ui_candidate(self):
        caption = "Prezydent Turcji wita prezydenta USA w Ankarze, 7 lipca 2026 r."
        text = "\n".join([
            f"[img2: {caption}]",
            caption,
            LONG_PARAGRAPH,
        ])
        candidates = photo_caption_candidates(text)
        assert [(item["line_index"], item["category"]) for item in candidates] == [
            (0, "image_marker"), (1, "image_description"),
        ]
        filtered = remove_photo_caption_lines(text)
        assert "[img2" not in filtered
        assert "Prezydent Turcji" not in filtered
        assert LONG_PARAGRAPH in filtered

    def test_onet_marker_credit_and_repeated_alt_are_all_candidates(self):
        caption = "Prezydent Turcji wita prezydenta USA w Ankarze, 7 lipca 2026 r."
        text = "\n".join([
            f"[img2: {caption}]",
            "ABDULLAH GUCLU / AFP",
            caption,
            LONG_PARAGRAPH,
        ])
        candidates = photo_caption_candidates(text)
        assert [item["line_index"] for item in candidates] == [0, 1, 2]
        filtered = remove_photo_caption_lines(text)
        assert "ABDULLAH" not in filtered
        assert caption not in filtered
        assert LONG_PARAGRAPH in filtered

    def test_histmag_short_credit_between_marker_and_repeated_alt_is_candidate(self):
        caption = "Makieta obozu, 2022 rok (fot. Drozdp), licencja CC BY-SA 4.0"
        text = "\n".join([
            f"[img3: {caption}]",
            "Drozdp / Portal historyczny Histmag.org",
            caption,
            LONG_PARAGRAPH,
        ])
        candidates = photo_caption_candidates(text)
        assert [item["line_index"] for item in candidates] == [0, 1, 2]
        assert candidates[1]["category"] == "image_credit"

    def test_copyright_and_abbreviated_illustrative_caption_detected(self):
        assert is_photo_caption_line("Rosyjskie czołgi. © Twitter | Kontakt6")
        assert is_photo_caption_line("Firma złożyła wniosek o upadłość (zdj. ilustracyjne)")

    def test_agencja_wyborcza_detected_without_fot_prefix(self):
        assert is_photo_caption_line("Krzysztof Gutkowski / Agencja Wyborcza.pl")

    def test_bloomberg_credit_line(self):
        assert is_photo_caption_line("Bloomberg")

    def test_interia_glued_caption_with_doubled_agency(self):
        # Prawdziwy podpis z interia.pl (dok. 9145) — ekstrakcja skleiła
        # podpis z podwojonym creditem agencji bez spacji.
        line = (
            "Mapy stworzone za pomocą Pokémon GO zasilają systemy "
            "nawigacyjne wojskowych dronowychBloombergBloomberg"
        )
        assert is_photo_caption_line(line)

    def test_interia_glued_uppercase_photographer_and_acronym(self):
        # Wersalikowe nazwisko fotografa sklejone z akronimem agencji.
        line = (
            "W Pokemon Go gracze skanowali masę znanych obiektów, "
            "tworząc nieświadomie mapy dla wojskaTHOMAS SAMSONAFP"
        )
        assert is_photo_caption_line(line)

    def test_glued_agency_credit_categorized_as_agency(self):
        text = "\n".join([
            LONG_PARAGRAPH,
            "Mapy stworzone za pomocą Pokémon GO zasilają systemy "
            "nawigacyjne wojskowych dronowychBloombergBloomberg",
        ])
        candidates = photo_caption_candidates(text)
        assert [item["category"] for item in candidates] == ["agency"]

    def test_allcaps_word_ending_like_acronym_is_not_split(self):
        assert not is_photo_caption_line("NA OBIAD BYŁA RZEPA")

    def test_publisher_own_agency_on_publisher_domain(self):
        text = f"{LONG_PARAGRAPH}\nFot. Krzysztof Gutkowski / Agencja Wyborcza.pl"
        for url in (
            "https://next.gazeta.pl/next/7,151003,32847569,artykul.html",
            "https://wyborcza.pl/7,75399,12345,artykul.html",
        ):
            candidates = photo_caption_candidates(text, url)
            assert [item["category"] for item in candidates] == ["own_or_private_archive"]

    def test_publisher_own_agency_on_foreign_domain_is_regular_agency(self):
        text = f"{LONG_PARAGRAPH}\nFot. Krzysztof Gutkowski / Agencja Wyborcza.pl"
        candidates = photo_caption_candidates(text, "https://www.onet.pl/informacje/artykul")
        assert [item["category"] for item in candidates] == ["agency"]

    def test_publisher_own_agency_without_url_is_regular_agency(self):
        text = f"{LONG_PARAGRAPH}\nFot. Krzysztof Gutkowski / Agencja Wyborcza.pl"
        candidates = photo_caption_candidates(text)
        assert [item["category"] for item in candidates] == ["agency"]


class TestClickbaitTitle:
    def test_clickbait(self):
        assert is_clickbait_title("Nie uwierzysz, co zrobił ten polityk")
        assert is_clickbait_title("Szokujące odkrycie naukowców")

    def test_normal_title(self):
        assert not is_clickbait_title("Rząd przyjął nowelizację ustawy o OZE")

    def test_none_title(self):
        assert not is_clickbait_title(None)


class TestComputeQuality:
    def _sections(self, temat=6, noise=0):
        secs = [{"type": "TEMAT", "original": LONG_PARAGRAPH * 3} for _ in range(temat)]
        secs += [{"type": "SZUM", "original": "Menu | Kontakt | Regulamin"} for _ in range(noise)]
        return secs

    def test_clean_article_scores_100(self):
        doc = _Doc(author="Jan Kowalski", title="Rzetelny tytuł artykułu")
        q = compute_quality(doc, self._sections(), model=None)
        assert q["score"] == 100
        assert q["penalties"] == {}
        assert q["llm_rubric"] is None

    def test_missing_author_penalty(self):
        q = compute_quality(_Doc(title="Tytuł"), self._sections(), model=None)
        assert q["penalties"]["missing_author"] == 10
        assert q["score"] == 90

    def test_stock_photo_source_penalty_capped(self):
        captions = "\n".join(["Fot. X / shutterstock"] * 5)
        secs = self._sections() + [{"type": "TEMAT", "original": captions}]
        q = compute_quality(_Doc(author="A", title="T"), secs, model=None)
        assert q["penalties"]["photo_sources"] == 15
        assert q["signals"]["photo_captions"] == 5
        assert q["signals"]["photo_caption_categories"] == {"stock": 5}
        assert q["signals"]["photo_source_penalty_details"] == {"stock": 15}
        assert len(q["signals"]["photo_caption_lines"]) == 5

    def test_photo_sources_are_weighted_by_provenance(self):
        captions = "\n".join([
            "Fot. Anna Nowak / archiwum prywatne",
            "Wu Hong / PAP",
            "Domena Publiczna/wikimedia",
            "Zdjęcie ilustracyjne / Shutterstock",
        ])
        secs = self._sections() + [{"type": "TEMAT", "original": captions}]
        q = compute_quality(_Doc(author="A", title="T"), secs, model=None)

        assert q["penalties"]["photo_sources"] == 6  # 0 + 1 + 2 + 3
        assert q["signals"]["photo_caption_categories"] == {
            "own_or_private_archive": 1,
            "agency": 1,
            "public_domain": 1,
            "illustrative": 1,
        }
        assert q["signals"]["photo_source_penalty_details"] == {
            "agency": 1, "public_domain": 2, "illustrative": 3,
        }

    def test_own_photo_source_is_not_penalized(self):
        secs = self._sections() + [{
            "type": "TEMAT", "original": "Fot. Anna Nowak / archiwum prywatne",
        }]
        q = compute_quality(_Doc(author="Anna Nowak", title="T"), secs, model=None)

        assert "photo_sources" not in q["penalties"]
        assert q["signals"]["photo_caption_categories"] == {"own_or_private_archive": 1}

    def test_publisher_own_agency_photo_is_not_penalized(self):
        secs = self._sections() + [{
            "type": "TEMAT", "original": "Fot. Krzysztof Gutkowski / Agencja Wyborcza.pl",
        }]
        doc = _Doc(author="Oliwia Ziółkowska", title="T",
                   url="https://next.gazeta.pl/next/7,151003,32847569,artykul.html")
        q = compute_quality(doc, secs, model=None)

        assert "photo_sources" not in q["penalties"]
        assert q["signals"]["photo_caption_categories"] == {"own_or_private_archive": 1}

    def test_publisher_agency_photo_on_foreign_portal_penalized_as_agency(self):
        secs = self._sections() + [{
            "type": "TEMAT", "original": "Fot. Krzysztof Gutkowski / Agencja Wyborcza.pl",
        }]
        doc = _Doc(author="A", title="T", url="https://www.onet.pl/informacje/artykul")
        q = compute_quality(doc, secs, model=None)

        assert q["penalties"]["photo_sources"] == 1
        assert q["signals"]["photo_caption_categories"] == {"agency": 1}

    def test_image_description_is_not_treated_as_a_photo_source(self):
        secs = self._sections() + [{
            "type": "TEMAT",
            "original": "[img1: Prezydent podczas konferencji]\nPrezydent podczas konferencji",
        }]
        q = compute_quality(_Doc(author="A", title="T"), secs, model=None)

        assert "photo_sources" not in q["penalties"]
        assert q["signals"]["photo_captions"] == 0

    def test_session_provided_but_no_document_images_rows_falls_back_to_text_scan(self):
        session = _fake_session([])
        secs = self._sections() + [{"type": "TEMAT", "original": "Fot. X / shutterstock"}]
        doc = _Doc(author="A", title="T", id=9265)
        q = compute_quality(doc, secs, model=None, session=session)

        assert q["penalties"]["photo_sources"] == 3
        assert q["signals"]["photo_caption_categories"] == {"stock": 1}

    def test_session_with_document_images_rows_used_instead_of_text_scan(self):
        """document_images is authoritative once populated — even when full_text
        contains a caption-looking line that isn't reflected there."""
        rows = [
            SimpleNamespace(caption_text="Fot. X / shutterstock", caption_category="stock"),
            SimpleNamespace(caption_text=None, caption_category=None),  # no caption found for this image
        ]
        session = _fake_session(rows)
        secs = self._sections() + [{"type": "TEMAT", "original": "Fot. Y / getty images"}]
        doc = _Doc(author="A", title="T", id=9265)
        q = compute_quality(doc, secs, model=None, session=session)

        assert q["penalties"]["photo_sources"] == 3
        assert q["signals"]["photo_captions"] == 1
        assert q["signals"]["photo_caption_categories"] == {"stock": 1}
        assert q["signals"]["photo_caption_lines"] == ["Fot. X / shutterstock"]

    def test_session_with_document_images_rows_all_uncategorized_means_no_penalty(self):
        """Rows exist (already checked at clean time) but none carry a caption —
        that is a real answer, not missing data, so no text-scan fallback."""
        rows = [SimpleNamespace(caption_text=None, caption_category=None)]
        session = _fake_session(rows)
        secs = self._sections() + [{"type": "TEMAT", "original": "Fot. Y / getty images"}]
        doc = _Doc(author="A", title="T", id=9265)
        q = compute_quality(doc, secs, model=None, session=session)

        assert "photo_sources" not in q["penalties"]
        assert q["signals"]["photo_captions"] == 0

    def test_session_without_doc_id_falls_back_to_text_scan(self):
        session = _fake_session([SimpleNamespace(caption_text="x", caption_category="stock")])
        secs = self._sections() + [{"type": "TEMAT", "original": "Fot. Y / getty images"}]
        doc = _Doc(author="A", title="T", id=None)
        q = compute_quality(doc, secs, model=None, session=session)

        # doc has no id -> DB path skipped entirely, session.scalars never called
        session.scalars.assert_not_called()
        assert q["signals"]["photo_caption_categories"] == {"stock": 1}

    def test_noise_share_penalty(self):
        secs = [
            {"type": "TEMAT", "original": "a" * 6000},
            {"type": "SZUM", "original": "b" * 2000},
            {"type": "REKLAMA", "original": "c" * 2000},
        ]
        q = compute_quality(_Doc(author="A", title="T"), secs, model=None)
        # 4000/10000 = 40% szumu → kara 20 (cap)
        assert q["penalties"]["noise_share"] == 20
        assert q["signals"]["noise_share"] == 0.4

    def test_short_text_penalty(self):
        secs = [{"type": "TEMAT", "original": "Krótka notka."}]
        q = compute_quality(_Doc(author="A", title="T"), secs, model=None)
        assert q["penalties"]["short_text"] == 10

    def test_clickbait_title_penalty(self):
        doc = _Doc(author="A", title="Nie uwierzysz, co się stało")
        q = compute_quality(doc, self._sections(), model=None)
        assert q["penalties"]["clickbait_title"] == 5

    def test_score_never_negative(self):
        secs = [
            {"type": "TEMAT", "original": "Fot. A / shutterstock\nFot. B / getty\nFot. C / PAP"},
            {"type": "SZUM", "original": "x" * 100000},
        ]
        q = compute_quality(_Doc(title="Szokujące! Nie uwierzysz"), secs, model=None)
        assert q["score"] >= 0

    def test_result_shape(self):
        q = compute_quality(_Doc(author="A", title="T"), self._sections(), model=None)
        assert set(q) == {"score", "penalties", "signals", "llm_rubric", "model", "computed_at"}
        assert q["model"] is None

    def test_separate_citations_chunk_sets_sources_floor(self, monkeypatch):
        monkeypatch.setattr(
            "library.article_quality._llm_rubric",
            lambda text, model, cited, press: {
                "zrodla": 0, "glebia": 0, "jezyk": 3,
                "uzasadnienie": "Model nie zauważył wydzielonej listy.",
            },
        )
        sections = self._sections() + [{
            "type": "SZUM",
            "original": "\n".join([
                "https://pmc.ncbi.nlm.nih.gov/articles/PMC8431537/",
                "https://pubmed.ncbi.nlm.nih.gov/30485934/",
                "https://pubmed.ncbi.nlm.nih.gov/21188562/",
            ]),
        }]
        q = compute_quality(_Doc(author="A", title="T"), sections, model="test-model")

        assert q["signals"]["cited_publications"] == 3
        assert q["llm_rubric"]["zrodla"] == 4
        assert q["penalties"]["llm_rubric"] == 16

    def test_references_chunk_is_not_penalized_as_noise(self):
        sections = self._sections() + [{
            "type": "SZUM",
            "original": "Źródła:\nhttps://pubmed.ncbi.nlm.nih.gov/30485934/",
        }]
        q = compute_quality(_Doc(author="A", title="T"), sections, model=None)

        assert "noise_share" not in q["penalties"]
        assert q["signals"]["noise_share"] == 0
        assert q["signals"]["reference_chars"] > 0

    def test_explicit_zrodla_type_needs_no_heading_heuristic(self):
        sections = self._sections() + [{
            "type": "ZRODLA",
            "original": "PMID 30485934",
        }]
        q = compute_quality(_Doc(author="A", title="T"), sections, model=None)

        assert "noise_share" not in q["penalties"]
        assert q["signals"]["reference_chars"] == len("PMID 30485934")

    def test_press_bibliography_sets_sources_floor(self, monkeypatch):
        monkeypatch.setattr(
            "library.article_quality._llm_rubric",
            lambda text, model, cited, press: {
                "zrodla": 1, "glebia": 2, "jezyk": 3,
                "uzasadnienie": "Model nie widział wydzielonej bibliografii.",
            },
        )
        sections = self._sections() + [{"type": "ZRODLA", "original": PRESS_BIBLIOGRAPHY}]
        q = compute_quality(_Doc(author="A", title="T"), sections, model="test-model")

        assert q["signals"]["press_bibliography"] == 5
        assert q["signals"]["press_bibliography_sources"][:2] == ["The Guardian", "Radio New Zealand"]
        assert q["llm_rubric"]["zrodla"] == 4
        assert q["penalties"]["llm_rubric"] == (15 - (4 + 2 + 3)) * 2

    def test_press_references_chunk_is_not_penalized_as_noise(self):
        sections = self._sections() + [{"type": "SZUM", "original": PRESS_BIBLIOGRAPHY}]
        q = compute_quality(_Doc(author="A", title="T"), sections, model=None)

        assert "noise_share" not in q["penalties"]
        assert q["signals"]["noise_share"] == 0
        assert q["signals"]["reference_chars"] == len(PRESS_BIBLIOGRAPHY)


class TestPressBibliography:
    def test_extracts_names_and_entries(self):
        entries = extract_press_bibliography(PRESS_BIBLIOGRAPHY)
        assert [item["source_name"] for item in entries] == [
            "The Guardian", "Radio New Zealand", "Time.com", "MSZ", "World Population Review",
        ]
        assert entries[0]["raw_entry"].startswith('The Guardian — "Papua New Guinea')

    def test_plain_heading_and_dash_bullets(self):
        text = "Źródła:\n- Raport GUS - dane za 2024 r.\n- NIK"
        entries = extract_press_bibliography(text)
        assert [item["source_name"] for item in entries] == ["Raport GUS", "NIK"]

    def test_no_heading_means_no_entries(self):
        text = "* The Guardian — artykuł\n* MSZ"
        assert extract_press_bibliography(text) == []

    def test_list_ends_at_first_non_bullet_line(self):
        text = "Źródła:\n* The Guardian — artykuł\nZwykły akapit treści.\n* To już nie bibliografia"
        entries = extract_press_bibliography(text)
        assert [item["source_name"] for item in entries] == ["The Guardian"]

    def test_bulletless_paragraph_under_heading_is_not_an_entry(self):
        text = "Źródła:\nWięcej informacji na stronie ministerstwa."
        assert extract_press_bibliography(text) == []


class TestIsReferencesSection:
    def test_press_bibliography_without_identifiers(self):
        assert is_references_section(PRESS_BIBLIOGRAPHY)

    def test_bold_heading_with_doi(self):
        assert is_references_section("**Źródła:**\nhttps://pubmed.ncbi.nlm.nih.gov/30485934/")

    def test_heading_without_any_entries(self):
        assert not is_references_section("Źródła:\n")

    def test_content_chunk_is_not_references(self):
        assert not is_references_section(LONG_PARAGRAPH)
