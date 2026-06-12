"""Unit tests for library.article_cleaner — portal artifact cleanup.

Pure-function tests on synthetic markdown fixtures, no DB/LLM/network.
"""

from library.article_cleaner import (
    _clean_lines_money,
    _clean_lines_onet,
    _clean_lines_wp,
    _detect_h2_ads,
    _is_portal_internal_link,
    clean_article_text,
)

LONG_PARAGRAPH = (
    "To jest długi akapit właściwej treści artykułu, który ma zdecydowanie ponad "
    "osiemdziesiąt znaków i powinien zostać zachowany po czyszczeniu."
)


class TestImageExtraction:
    def test_inline_image_replaced_with_marker(self):
        text = f"Początek ![Opis zdjęcia](https://example.com/foto.jpg) dalszy tekst.\n\n{LONG_PARAGRAPH}"
        result = clean_article_text(text)
        assert result["images"] == [{"alt": "Opis zdjęcia", "url": "https://example.com/foto.jpg"}]
        assert "[img0: Opis zdjęcia]" in result["text"]

    def test_standalone_image_line_removed_but_collected(self):
        text = f"{LONG_PARAGRAPH}\n\n![Opis zdjęcia](https://example.com/foto.jpg)\n\nDrugi akapit."
        result = clean_article_text(text)
        assert result["images"] == [{"alt": "Opis zdjęcia", "url": "https://example.com/foto.jpg"}]
        # Linia z samym markerem [imgN] jest usuwana z tekstu
        assert "[img0" not in result["text"]
        assert "Drugi akapit." in result["text"]

    def test_image_with_empty_url_removed(self):
        text = f"Przed ![jakiś alt]() po.\n\n{LONG_PARAGRAPH}"
        result = clean_article_text(text)
        assert result["images"] == []
        assert "[img0" not in result["text"]

    def test_duplicate_image_url_collected_once(self):
        text = (
            f"Akapit ![Foto](https://example.com/a.jpg) pierwszy.\n\n"
            f"Akapit ![Foto](https://example.com/a.jpg) drugi.\n\n{LONG_PARAGRAPH}"
        )
        result = clean_article_text(text)
        assert len(result["images"]) == 1

    def test_tracking_pixel_without_alt_and_extension_removed(self):
        text = f"Przed ![](https://example.com/track) po.\n\n{LONG_PARAGRAPH}"
        result = clean_article_text(text)
        assert result["images"] == []

    def test_image_without_alt_but_with_extension_kept(self):
        text = f"Przed ![](https://example.com/zdjecie.png) po.\n\n{LONG_PARAGRAPH}"
        result = clean_article_text(text)
        assert result["images"] == [{"alt": "", "url": "https://example.com/zdjecie.png"}]
        assert "[img0]" in result["text"]


class TestLinkExtraction:
    def test_link_replaced_with_marker(self):
        text = f"Zobacz [pełny raport](https://example.com/raport.pdf) w sieci.\n\n{LONG_PARAGRAPH}"
        result = clean_article_text(text)
        assert result["links"] == [{"text": "pełny raport", "url": "https://example.com/raport.pdf"}]
        assert "pełny raport [link0]" in result["text"]

    def test_portal_internal_link_keeps_text_only(self):
        text = f"Tag: [polityka](https://www.wp.pl/tag/polityka) w artykule.\n\n{LONG_PARAGRAPH}"
        result = clean_article_text(text)
        assert result["links"] == []
        assert "polityka" in result["text"]
        assert "[link0]" not in result["text"]

    def test_link_with_huge_tracking_url_removed(self):
        url = "https://ads.example.com/" + "a" * 210
        text = f"Promocja [Kup teraz]({url}) tutaj.\n\n{LONG_PARAGRAPH}"
        result = clean_article_text(text)
        assert result["links"] == []
        assert "Kup teraz" not in result["text"]


class TestPortalInternalLink:
    def test_tag_and_author_urls_are_internal(self):
        assert _is_portal_internal_link("https://wiadomosci.wp.pl/tag/iran")
        assert _is_portal_internal_link("https://www.money.pl/archiwum/autor/jan-kowalski")
        assert _is_portal_internal_link("https://wiadomosci.onet.pl/kraj")

    def test_regular_article_url_is_not_internal(self):
        assert not _is_portal_internal_link("https://example.com/artykul-o-gospodarce.html")


class TestGenericLineCleaning:
    def test_portal_phrases_removed(self):
        text = (
            f"{LONG_PARAGRAPH}\n\nREKLAMA\n\nLubię to\n\n---\n\n123\n\n"
            f"00:09 / 00:16\n\nOdtwórz/Pauza\n\nDrugi akapit treści."
        )
        result = clean_article_text(text)
        assert "REKLAMA" not in result["text"]
        assert "Lubię to" not in result["text"]
        assert "---" not in result["text"]
        assert "123" not in result["text"]
        assert "00:09 / 00:16" not in result["text"]
        assert "Odtwórz/Pauza" not in result["text"]
        assert LONG_PARAGRAPH in result["text"]
        assert "Drugi akapit treści." in result["text"]

    def test_h2_ad_section_removed_until_long_paragraph(self):
        text = (
            f"Wstęp artykułu, który jest dość długi i zawiera ponad osiemdziesiąt znaków treści właściwej.\n\n"
            f"## Zobacz wideo\n\n"
            f"![miniatura](https://v.wp.pl/x.jpg)\n\n"
            f"krótka linia wstawki\n\n"
            f"{LONG_PARAGRAPH}"
        )
        result = clean_article_text(text)
        assert "Zobacz wideo" not in result["text"]
        assert "krótka linia wstawki" not in result["text"]
        assert LONG_PARAGRAPH in result["text"]

    def test_detect_h2_ads_finds_h2_followed_by_image(self):
        text = "## Wstawka wideo\n\n![mini](https://example.com/m.jpg)\n\nTekst."
        assert _detect_h2_ads(text) == {"## Wstawka wideo"}

    def test_detect_h2_ads_ignores_h2_with_text_content(self):
        text = "## Normalny śródtytuł\n\nZwykły akapit tekstu po śródtytule.\n"
        assert _detect_h2_ads(text) == set()


class TestNormalization:
    def test_nbsp_replaced_and_blank_lines_collapsed(self):
        text = f"Pierwszy\xa0akapit.\n\n\n\n\n{LONG_PARAGRAPH}"
        result = clean_article_text(text)
        assert "Pierwszy akapit." in result["text"]
        assert "\n\n\n" not in result["text"]

    def test_universal_footer_marker_cuts_text(self):
        text = f"{LONG_PARAGRAPH}\n\nDziękujemy, że przeczytałaś/eś nasz artykuł.\n\nStopka portalu."
        result = clean_article_text(text)
        assert LONG_PARAGRAPH in result["text"]
        assert "Stopka portalu." not in result["text"]


class TestOnetCleaning:
    def test_onet_audio_player_and_date_removed(self):
        lines = [
            "#### Posłuchaj artykułu",
            "x1.5",
            "17 marca 2026, 12:31",
            "5 min czytania",
            "Treść artykułu onet.",
        ]
        assert _clean_lines_onet(lines) == ["Treść artykułu onet."]

    def test_onet_portal_detected_from_url(self):
        text = f"Posłuchaj artykułu\n\n{LONG_PARAGRAPH}"
        result = clean_article_text(text, url="https://wiadomosci.onet.pl/swiat/jakis-artykul")
        assert "Posłuchaj artykułu" not in result["text"]
        assert LONG_PARAGRAPH in result["text"]


class TestMoneyCleaning:
    def test_money_tags_line_and_share_removed(self):
        lines = [
            "Udostępnij",
            "gospodarka elektrownia atomowa rosja +1",
            "24 marca 2026, 12:26",
            "Treść artykułu money.",
        ]
        assert _clean_lines_money(lines) == ["Treść artykułu money."]


class TestWpCleaning:
    def test_wp_comments_author_and_tags_removed(self):
        lines = [
            "Udostępnij",
            "5 komentarzy",
            "iran rakiety balistyczne europa +3",
            "Jan Kowalski, dziennikarz Wirtualnej Polski",
            "Treść artykułu wp.",
        ]
        assert _clean_lines_wp(lines) == ["Treść artykułu wp."]
