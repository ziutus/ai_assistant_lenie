"""Unit tests for library.article_cleaner — portal artifact cleanup.

Pure-function tests on synthetic markdown fixtures, no DB/LLM/network.
"""

import datetime

from library.article_cleaner import (
    _clean_lines_money,
    _clean_lines_onet,
    _clean_lines_ithardware,
    _clean_lines_interia,
    _is_adjacent_tag_links_line,
    _clean_lines_wp,
    _detect_h2_ads,
    _is_portal_internal_link,
    _strip_leading_onet_ai_summary,
    _strip_interia_chrome_blocks,
    clean_article_text,
    resolve_relative_publication_date,
)
from library.article_extractor import _detect_portal, extract_article_by_markers

LONG_PARAGRAPH = (
    "To jest długi akapit właściwej treści artykułu, który ma zdecydowanie ponad "
    "osiemdziesiąt znaków i powinien zostać zachowany po czyszczeniu."
)


class TestGazetaExtraction:
    URL = "https://wiadomosci.gazeta.pl/swiat/7,123,artykul.html"

    def test_detects_gazeta_portal(self):
        assert _detect_portal(self.URL) == "gazeta"

    def test_footer_overrides_llm_end_before_embedded_recommendation(self):
        markdown = "\n\n".join([
            "Pierwsze zdanie właściwego artykułu ma zdecydowanie więcej niż czterdzieści znaków.",
            "Zdanie błędnie wskazane przez model jako koniec artykułu, choć tekst trwa dalej.",
            "Czytaj także:",
            "SUBSKRYPCJA",
            "[Polecany tekst](https://wyborcza.pl/polecany)",
            "Dalszy akapit artykułu znajdujący się za osadzoną kartą rekomendacji portalu.",
            "- To jest prawidłowe ostatnie zdanie całego artykułu wypowiedziane przez polityka.",
            "REKLAMA",
            "*Źródło: PAP*",
            "Dziękujemy za przeczytanie",
        ])
        markers = {
            "article_first_sentence": "Pierwsze zdanie właściwego artykułu ma zdecydowanie więcej niż czterdzieści znaków.",
            "article_last_sentence": "Zdanie błędnie wskazane przez model jako koniec artykułu, choć tekst trwa dalej.",
        }

        result = extract_article_by_markers(markdown, markers, url=self.URL)

        assert "prawidłowe ostatnie zdanie" in result
        assert "Źródło: PAP" not in result

    def test_cleaner_removes_embedded_recommendation_but_keeps_following_text(self):
        text = "\n\n".join([
            LONG_PARAGRAPH,
            "Czytaj także:",
            "SUBSKRYPCJA",
            "[Polecany tekst](https://wyborcza.pl/polecany)",
            "Dalszy akapit właściwego artykułu, który znajduje się za kartą polecanego tekstu "
            "i musi pozostać w ostatecznie oczyszczonej treści dokumentu.",
            "*Źródło: PAP*",
        ])

        result = clean_article_text(text, url=self.URL)["text"]

        assert "Dalszy akapit właściwego artykułu" in result
        assert "Czytaj także" not in result
        assert "SUBSKRYPCJA" not in result
        assert "Polecany tekst" not in result
        assert "Źródło: PAP" not in result

    def test_gallery_and_homepage_controls_removed_but_article_sentence_kept(self):
        text = "\n\n".join([
            "Otwórz galerię (3)",
            "[przejdź na](https://www.gazeta.pl/0%2C0.html?utm_campaign=test)",
            "Reporter powiedział: przejdź na drugą stronę dokumentu i otwórz galerię sztuki.",
            LONG_PARAGRAPH,
        ])

        result = clean_article_text(text, url=self.URL)["text"]

        assert "Otwórz galerię (3)" not in result
        assert "przejdź na [link" not in result
        assert "przejdź na drugą stronę" in result
        assert LONG_PARAGRAPH in result


class TestImageExtraction:
    def test_inline_image_replaced_with_marker(self):
        text = f"Początek ![Opis zdjęcia](https://example.com/foto.jpg) dalszy tekst.\n\n{LONG_PARAGRAPH}"
        result = clean_article_text(text)
        assert result["images"] == [{"alt": "Opis zdjęcia", "url": "https://example.com/foto.jpg"}]
        assert "[img0: Opis zdjęcia]" in result["text"]

    def test_standalone_image_line_preserved_for_quality_and_collected(self):
        text = f"{LONG_PARAGRAPH}\n\n![Opis zdjęcia](https://example.com/foto.jpg)\n\nDrugi akapit."
        result = clean_article_text(text)
        # Linia bezpośrednio po markerze trafia do caption_text/caption_category
        # (article_quality.photo_caption_candidates), nawet gdy to zwykły akapit,
        # nie faktyczny podpis — to znana niedokładność współdzielonej heurystyki.
        assert result["images"] == [{
            "alt": "Opis zdjęcia", "url": "https://example.com/foto.jpg",
            "caption_text": "Drugi akapit.", "caption_category": "image_credit",
        }]
        # Marker pozostaje dla quality/UI; generator embeddingów filtruje jego kopię.
        assert "[img0: Opis zdjęcia]" in result["text"]
        assert "Drugi akapit." in result["text"]

    def test_standalone_image_with_stock_caption_categorized(self):
        text = (
            f"{LONG_PARAGRAPH}\n\n![Zdjęcie](https://example.com/foto.jpg)\n\n"
            f"Dmytro Buiansky / shutterstock\n\n{LONG_PARAGRAPH}"
        )
        result = clean_article_text(text)
        assert result["images"] == [{
            "alt": "Zdjęcie", "url": "https://example.com/foto.jpg",
            "caption_text": "Dmytro Buiansky / shutterstock",
            "caption_category": "stock",
        }]
        # Kategoria z jednoznacznym słowem-kluczem (stock) — usuwana z treści,
        # dane podpisu przeżyły już wyżej w extracted_images.
        assert "Dmytro Buiansky / shutterstock" not in result["text"]
        assert "[img0: Zdjęcie]" in result["text"]

    def test_credit_line_before_exact_alt_repeat_removed(self):
        # Wzorzec z onet.pl/wodne-sprawy (dok. 9034): [imgN: alt] → linia-credit
        # bez rozpoznawalnego słowa-klucza agencji → linia dosłownie powtarzająca alt.
        text = (
            f"{LONG_PARAGRAPH}\n\n![Panthalassa](https://example.com/foto.jpg)\n\n"
            f"Panthalassa/x / Wodne Sprawy\n\nPanthalassa\n\n{LONG_PARAGRAPH}"
        )
        result = clean_article_text(text)
        assert "[img0: Panthalassa]" in result["text"]
        assert "Panthalassa/x / Wodne Sprawy" not in result["text"]
        assert "\nPanthalassa\n" not in result["text"]
        assert result["text"].count(LONG_PARAGRAPH) == 2

    def test_credit_line_without_following_alt_repeat_kept(self):
        # Bez potwierdzającej linii-alt-repeat sama krótka linia po markerze
        # NIE jest usuwana (mogłaby być zwykłym akapitem) — tylko para jest bezpieczna.
        text = (
            f"{LONG_PARAGRAPH}\n\n![Panthalassa](https://example.com/foto.jpg)\n\n"
            f"Zupełnie inna krótka linia\n\n{LONG_PARAGRAPH}"
        )
        result = clean_article_text(text)
        assert "Zupełnie inna krótka linia" in result["text"]

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

    def test_onet_recommendation_and_channel_chrome_removed(self):
        lines = [
            "CZYTAJ TAKŻE",
            "ZOBACZ RÓWNIEŻ",
            "Top 5 treści Premium",
            "Więcej takich artykułów znajdziesz na stronie głównej Onetu",
            "Powiązane tematy: Karol Nawrocki Wołodymyr Zełenski Ukraina",
            "Opracowanie: Mateusz Bałuka",
            "**PRZECZYTAJ CAŁY WYWIAD** [link9]",
            "Dodaj w Google",
            "Wróć na",
            "Jesteś w strefie",
            "Treść artykułu onet.",
        ]
        assert _clean_lines_onet(lines) == ["Treść artykułu onet."]

    def test_onet_opracowanie_prefix_requires_following_text(self):
        # "Opracowanie:" bez nazwiska nie powinno paść ofiarą zbyt zachłannego regexu
        lines = ["Opracowanie:", "Treść artykułu onet."]
        assert _clean_lines_onet(lines) == ["Opracowanie:", "Treść artykułu onet."]

    def test_strips_leading_five_bullet_ai_summary_leak(self):
        # Box "Poniżej streszczenie artykułu: Skrót przygotowany przez Onet
        # Czat z AI" generuje zawsze 5 punktów; ekstrakcja czasem gubi jego
        # nagłówek i zostawia same punkty jako pozorny początek artykułu
        # (zweryfikowane na żywo na onet.pl/informacje/magazynkontakt/...).
        text = (
            "* Punkt pierwszy streszczenia AI.\n"
            "* Punkt drugi streszczenia AI.\n"
            "* Punkt trzeci streszczenia AI.\n"
            "* Punkt czwarty streszczenia AI.\n"
            "* Punkt piąty streszczenia AI.\n\n"
            f"**{LONG_PARAGRAPH}**"
        )
        result = _strip_leading_onet_ai_summary(text)
        assert "Punkt pierwszy" not in result
        assert "Punkt piąty" not in result
        assert LONG_PARAGRAPH in result

    def test_does_not_strip_leading_bullets_with_wrong_count(self):
        # Tylko dokładnie 5 punktów jest bezpiecznym sygnałem (stały format
        # boxu AI) — 4 lub 6 punktów to może być prawdziwa lista w artykule.
        text = (
            "* Punkt pierwszy.\n* Punkt drugi.\n* Punkt trzeci.\n* Punkt czwarty.\n\n"
            f"{LONG_PARAGRAPH}"
        )
        assert _strip_leading_onet_ai_summary(text) == text

    def test_does_not_strip_five_bullets_mid_article(self):
        # Sygnał działa tylko na samym początku tekstu — pięć punktów
        # gdzieś w środku prawdziwego artykułu (np. lista "kluczowych faktów")
        # zostaje nietknięte.
        text = (
            f"{LONG_PARAGRAPH}\n\n"
            "* Punkt pierwszy.\n* Punkt drugi.\n* Punkt trzeci.\n"
            "* Punkt czwarty.\n* Punkt piąty.\n"
        )
        assert _strip_leading_onet_ai_summary(text) == text

    def test_ai_summary_leak_stripped_end_to_end_via_clean_article_text(self):
        text = (
            "* Punkt pierwszy streszczenia AI.\n"
            "* Punkt drugi streszczenia AI.\n"
            "* Punkt trzeci streszczenia AI.\n"
            "* Punkt czwarty streszczenia AI.\n"
            "* Punkt piąty streszczenia AI.\n\n"
            f"**{LONG_PARAGRAPH}**"
        )
        result = clean_article_text(text, url="https://www.onet.pl/informacje/onetwiadomosci/jakis-artykul")
        assert "Punkt pierwszy" not in result["text"]
        assert LONG_PARAGRAPH in result["text"]


class TestInteriaCleaning:
    URL = "https://wydarzenia.interia.pl/bliski-wschod/news-jakis-artykul,nId,1"

    def test_nav_menu_block_removed_but_article_kept(self):
        text = (
            f"{LONG_PARAGRAPH}\n\n"
            "Polska\nŚwiat\nWydarzenia lokalne\nOkiem Interii\nWojna w Ukrainie\n"
            "Pogoda\nRedakcja\nReligia\nFelietoniści\nRaporty\nBaza wiedzy\nZielona Interia\n\n"
            f"{LONG_PARAGRAPH}"
        )
        result = _strip_interia_chrome_blocks(text)
        assert "Okiem Interii" not in result
        assert result.count(LONG_PARAGRAPH) == 2

    def test_reactions_block_removed(self):
        text = f"{LONG_PARAGRAPH}\n\nSuper\nHahaha\nSzok\nSmutny\nZły\n\n{LONG_PARAGRAPH}"
        result = _strip_interia_chrome_blocks(text)
        assert "Hahaha" not in result

    def test_single_reaction_word_in_real_content_kept(self):
        # Pojedyncze słowo z paska reakcji, poza pełną sekwencją, to może być
        # zwykła treść — usuwamy tylko całą, dokładną sekwencję 5 etykiet.
        text = f"{LONG_PARAGRAPH}\n\nSzok\n\n{LONG_PARAGRAPH}"
        assert _strip_interia_chrome_blocks(text) == text

    def test_interia_share_audio_and_timestamps_removed(self):
        lines = [
            "Udostępnij", "Odsłuchaj artykuł", "W skrócie", "Zobacz również:",
            "11 minut temu", "2 godziny temu",
            "wczoraj, 22:30", "Treść artykułu interia.",
        ]
        assert _clean_lines_interia(lines) == ["Treść artykułu interia."]

    def test_interia_portal_detected_end_to_end(self):
        text = (
            "Polska\nŚwiat\nWydarzenia lokalne\nOkiem Interii\nWojna w Ukrainie\n"
            "Pogoda\nRedakcja\nReligia\nFelietoniści\nRaporty\nBaza wiedzy\nZielona Interia\n\n"
            f"{LONG_PARAGRAPH}\n\nUdostępnij\n\n11 minut temu"
        )
        result = clean_article_text(text, url=self.URL)
        assert "Okiem Interii" not in result["text"]
        assert "Udostępnij" not in result["text"]
        assert "11 minut temu" not in result["text"]
        assert LONG_PARAGRAPH in result["text"]

    def test_audio_ai_disclaimer_removed_generically(self):
        # Ta sama etykieta wystąpiła już na onet.pl i interia.pl — reguła
        # generyczna, niezależna od portalu.
        lines = [
            "Audio generowane przez AI (ElevenLabs) i może zawierać błędy",
            "Treść artykułu.",
        ]
        result = clean_article_text(
            "\n\n".join(lines), url="https://wydarzenia.interia.pl/x,nId,1"
        )
        assert "ElevenLabs" not in result["text"]
        assert "Treść artykułu." in result["text"]


class TestResolveRelativePublicationDate:
    # dok. 8865 (interia.pl): chunk SZUM zawierał dokładnie "Wczoraj, 12:58",
    # ingested_at = 2026-04-13 07:10:45 -> published_on = 2026-04-12.
    INGESTED_AT = datetime.datetime(2026, 4, 13, 7, 10, 45)

    def test_yesterday_case_insensitive(self):
        result = resolve_relative_publication_date("Wczoraj, 12:58", self.INGESTED_AT)
        assert result == datetime.date(2026, 4, 12)

    def test_yesterday_lowercase(self):
        result = resolve_relative_publication_date("wczoraj, 22:30", self.INGESTED_AT)
        assert result == datetime.date(2026, 4, 12)

    def test_today(self):
        result = resolve_relative_publication_date("Dziś, 06:00", self.INGESTED_AT)
        assert result == datetime.date(2026, 4, 13)

    def test_today_full_word(self):
        result = resolve_relative_publication_date("Dzisiaj, 19:06", self.INGESTED_AT)
        assert result == datetime.date(2026, 4, 13)

    def test_hours_ago_crosses_midnight(self):
        # 07:10 minus 10 godzin = poprzedni dzień
        result = resolve_relative_publication_date("10 godzin temu", self.INGESTED_AT)
        assert result == datetime.date(2026, 4, 12)

    def test_hours_ago_same_day(self):
        result = resolve_relative_publication_date("2 godziny temu", self.INGESTED_AT)
        assert result == datetime.date(2026, 4, 13)

    def test_minutes_ago(self):
        result = resolve_relative_publication_date("30 minut temu", self.INGESTED_AT)
        assert result == datetime.date(2026, 4, 13)

    def test_found_among_other_lines(self):
        text = f"{LONG_PARAGRAPH}\n\nWczoraj, 12:58\n\n{LONG_PARAGRAPH}"
        assert resolve_relative_publication_date(text, self.INGESTED_AT) == datetime.date(2026, 4, 12)

    def test_no_match_returns_none(self):
        assert resolve_relative_publication_date(LONG_PARAGRAPH, self.INGESTED_AT) is None

    def test_no_ingested_at_returns_none(self):
        assert resolve_relative_publication_date("Wczoraj, 12:58", None) is None

    def test_empty_text_returns_none(self):
        assert resolve_relative_publication_date("", self.INGESTED_AT) is None


class TestMoneyCleaning:
    def test_money_tags_line_and_share_removed(self):
        lines = [
            "Udostępnij",
            "gospodarka elektrownia atomowa rosja +1",
            "24 marca 2026, 12:26",
            "Treść artykułu money.",
        ]
        assert _clean_lines_money(lines) == ["Treść artykułu money."]

    def test_money_comments_audio_and_share_controls_removed(self):
        lines = [
            "25 komentarzy",
            "Słuchaj",
            "Udostępnij na Facebooku Udostępnij na X Udostępnij na WhatsApp Kopiuj link",
            "Treść artykułu money.",
        ]
        assert _clean_lines_money(lines) == ["Treść artykułu money."]

    def test_money_author_artifact_and_contextual_source_logo_removed(self):
        lines = [
            "jacek.losik@grupawp.plo autorze",
            "Źródło artykułu:",
            "",
            "T",
            "The Wall Street Journal",
            "Litera T w treści artykułu pozostaje.",
        ]
        assert _clean_lines_money(lines) == [
            "The Wall Street Journal",
            "Litera T w treści artykułu pozostaje.",
        ]

    def test_money_author_bio_paragraph_removed(self):
        lines = [
            "Treść artykułu money.",
            "",
            "Dziennikarz portalu finansowego money.pl. Specjalizuje się w energetyce.",
            "",
            "przemyslaw.ciszak@grupawp.plo autorze",
            "Źródło artykułu:",
        ]
        assert _clean_lines_money(lines) == ["Treść artykułu money.", "", ""]

    def test_money_paragraph_not_removed_without_author_email_marker(self):
        lines = [
            "Treść artykułu money.",
            "",
            "Zwykły akapit, po którym nie ma widgetu o autorze.",
        ]
        assert _clean_lines_money(lines) == lines


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

    def test_wp_audio_and_share_controls_removed(self):
        lines = [
            "Słuchaj",
            "Udostępnij na Facebooku",
            "Udostępnij na X",
            "Udostępnij na WhatsApp",
            "Kopiuj link",
            "Treść artykułu wp.",
        ]
        assert _clean_lines_wp(lines) == ["Treść artykułu wp."]

    def test_o2_header_and_split_tags_removed(self):
        # o2.pl: nagłówek strony + tagi rozbite na osobne linie zakończone licznikiem "+N"
        lines = [
            "Zaloguj",
            "Obserwuj nas na:",
            "Źródło zdjęć: © Facebook, Pixabay",
            "3 lutego 2026, 13:51",
            "Treść artykułu o2.",
            "sztuczna inteligencja",
            "polska ukraina",
            "+3",
        ]
        assert _clean_lines_wp(lines) == ["Treść artykułu o2."]

    def test_o2_comments_disabled_notice_removed(self):
        lines = [
            "Treść artykułu o2.",
            "Wyłączono komentarze",
            "Jako redakcja Wirtualnej Polski doceniamy zaangażowanie naszych czytelników w komentarzach.",
            "Redakcja serwisu o2",
        ]
        assert _clean_lines_wp(lines) == ["Treść artykułu o2."]

    def test_o2_tag_like_lines_kept_without_counter(self):
        # Krótkie linie z małych liter NIE są usuwane, gdy nie kończą się licznikiem "+N"
        lines = [
            "krótka linia z małych liter",
            "Treść artykułu o2.",
        ]
        assert _clean_lines_wp(lines) == lines

    def test_wp_newsletter_block_removed_but_article_content_kept(self):
        lines = [
            "PREMIUM Zapisz się na newsletter!",
            "Newsy, wywiady, śledztwa i reportaże w Twojej skrzynce co tydzień - zawsze za darmo.",
            "Zapisz mnie",
            "Zapisz mnie na liście uczestników spotkania.",
        ]
        assert _clean_lines_wp(lines) == ["Zapisz mnie na liście uczestników spotkania."]

    def test_wp_author_email_artifact_removed_but_normal_email_kept(self):
        lines = [
            "Lukasz.Maziewski@grupawp.plo autorze",
            "Kontakt do autora: autor@grupawp.pl",
        ]
        assert _clean_lines_wp(lines) == ["Kontakt do autora: autor@grupawp.pl"]

    def test_wp_author_bio_paragraph_removed(self):
        lines = [
            "Treść artykułu wp.",
            "",
            "Dziennikarz działu technologii Wirtualnej Polski.",
            "",
            "lukasz.maziewski@grupawp.plo autorze",
        ]
        assert _clean_lines_wp(lines) == ["Treść artykułu wp.", "", ""]


class TestSafeUiArtifacts:
    def test_ad_block_markers_removed_without_touching_surrounding_paragraphs(self):
        before = "Akapit przed blokiem reklamowym pozostaje w artykule."
        after = "Akapit po bloku reklamowym również pozostaje w artykule."
        text = f"{before}\n\nREKLAMA\nKONIEC REKLAMY\n\n{after}"

        result = clean_article_text(text)["text"]

        assert "REKLAMA" not in result
        assert before in result
        assert after in result

    def test_generic_recommendations_video_markers_and_separator_removed(self):
        text = "\n".join([
            "Dalszy ciąg artykułu pod materiałem wideo",
            "**Zobacz także:** **Polecany materiał** [link0]",
            "* **Czytaj więcej:** **Inny materiał** [link1]",
            "|",
            LONG_PARAGRAPH,
        ])
        result = clean_article_text(text)["text"]
        assert result == LONG_PARAGRAPH

    def test_onet_ai_and_premium_labels_removed(self):
        lines = [
            "Zapytaj o więcej Onet Czat z AI [link0]",
            "Więcej pogłębionych treści",
            "Więcej treści premium dla Ciebie",
            "Treść artykułu.",
        ]
        assert _clean_lines_onet(lines) == ["Treść artykułu."]

    def test_ithardware_player_controls_are_domain_scoped(self):
        lines = ["Dalsza część artykulu pod video", "Play", "ad", "Treść artykułu."]
        assert _clean_lines_ithardware(lines) == ["Dalsza część artykulu pod video", "Treść artykułu."]

        text = "\n".join(lines)
        result = clean_article_text(text, url="https://ithardware.pl/aktualnosci/test.html")["text"]
        assert result == "Treść artykułu."

        unrelated = clean_article_text("Play\nad\nTreść artykułu.", url="https://example.com/article")["text"]
        assert "Play" in unrelated
        assert "ad" in unrelated

    def test_onet_adjacent_recommendation_cards_do_not_merge_or_remove_article(self):
        cards = (
            "Więcej treści premium dla Ciebie\n\n"
            "[![Pierwsza rekomendacja](https://cdn.example/1.jpg)\n\n"
            "#### Pierwsza rekomendacja](https://wiadomosci.onet.pl/a/1)"
            "[![Druga rekomendacja](https://cdn.example/2.jpg)\n\n"
            "#### Druga rekomendacja](https://wiadomosci.onet.pl/a/2)"
        )
        result = clean_article_text(
            f"{cards}\n\n{LONG_PARAGRAPH}",
            url="https://www.onet.pl/informacje/onetwiadomosci/test",
        )["text"]

        assert "Pierwsza rekomendacja" not in result
        assert "Druga rekomendacja" not in result
        assert LONG_PARAGRAPH in result


class TestAdjacentTagLinks:
    def test_detects_wp_and_money_tag_only_lines(self):
        assert _is_adjacent_tag_links_line(
            '[czołgi](/tag/czolgi)[rosja](/tag/rosja)'
        )
        assert _is_adjacent_tag_links_line(
            '[afryka](https://www.money.pl/wiadomosci/afryka.html "afryka")'
            '[rosja](https://www.money.pl/wiadomosci/rosja.html "rosja")'
        )

    def test_does_not_remove_adjacent_article_links_or_inline_sentence(self):
        article_links = (
            '[Pierwszy artykuł](https://example.com/1)'
            '[Drugi artykuł](https://example.com/2)'
        )
        inline = 'Zobacz [tag](/tag/test) w treści zdania.'
        assert not _is_adjacent_tag_links_line(article_links)
        assert not _is_adjacent_tag_links_line(inline)

        result = clean_article_text(f"{article_links}\n{inline}")["text"]
        assert "Pierwszy artykuł" in result
        assert "Drugi artykuł" in result
        assert "w treści zdania" in result

    def test_cleaner_removes_adjacent_tag_block(self):
        tags = '[czołgi](/tag/czolgi)[rosja](/tag/rosja)[militaria](/tag/militaria)'
        result = clean_article_text(f"{LONG_PARAGRAPH}\n{tags}", url="https://tech.wp.pl/test")["text"]
        assert result == LONG_PARAGRAPH


class TestBankierExtraction:
    URL = "https://www.bankier.pl/wiadomosc/Jakis-artykul-1234567.html"

    # Kształt zdjęty z realnego dokumentu (bankier.pl, 2026-02) — menu nagłówka
    # skrócone do reprezentatywnej próbki markerów.
    RAW_PAGE = "\n".join([
        "GIEŁDATytuł strony w tagu <title>",
        "Podziel się",
        "Skomentuj",
        "21",
        "Newsletter",
        "Rynki",
        "Giełda",
        "Waluty",
        "Zaloguj się / Zarejestruj",
        "REKLAMA",
        "Bankier.plRynkiGiełdaWiadomości",
        "InneNotowania GPWESPI/EBIGiełdy światoweRekomendacjeKalendariumDywidendyNarzędziaPortfelForum",
        "Ważny krok ws. budowy małych reaktorów jądrowych nad Wisłą",
        "publikacja",
        "2026-02-25 08:10",
        "",
        LONG_PARAGRAPH,
        "",
        "mcb/ osz/",
        "",
        "Źródło:",
        "PAP Biznes",
        "tematy",
        "pknorlen",
        "Polska elektrownia jądrowa",
        "Komentarze\xa0(21)",  # bankier.pl łączy oba słowa twardą spacją
        "dodaj komentarz",
        "miketheripper2026-02-25 15:28",
        "0",
        "1",
        "\"Nad Wisłą\" - będą lewitować czy wisieć?",
        "Powiązane: pknorlen",
        "Paweł Wojtunik wchodzi do zarządu Orlenu",
        "Notowania",
        "PKNORLEN",
        "114,56-0,47%",
        "Bankier.pl na skróty",
        "Giełda",
        "WIG30",
    ])

    def test_detects_bankier_portal(self):
        assert _detect_portal(self.URL) == "bankier"

    def test_cleaner_strips_nav_metadata_comments_and_footer_but_keeps_article(self):
        result = clean_article_text(self.RAW_PAGE, url=self.URL)["text"]

        assert LONG_PARAGRAPH in result

        # Górne menu nagłówka i breadcrumb/podmenu
        assert "Podziel się" not in result
        assert "Newsletter" not in result
        assert "Zaloguj się / Zarejestruj" not in result
        assert "Bankier.plRynkiGiełdaWiadomości" not in result
        assert "InneNotowania" not in result

        # Metadane publikacji nad artykułem
        assert "publikacja" not in result
        assert "2026-02-25 08:10" not in result

        # Źródło i tagi po artykule
        assert "Źródło:" not in result
        assert "PAP Biznes" not in result
        assert "pknorlen" not in result

        # Komentarze, powiązane artykuły, widget notowań, stopka-sitemapa
        assert "Komentarze (21)" not in result
        assert "będą lewitować" not in result
        assert "Powiązane: pknorlen" not in result
        assert "Paweł Wojtunik" not in result
        assert "PKNORLEN" not in result
        assert "Bankier.pl na skróty" not in result
        assert "WIG30" not in result
