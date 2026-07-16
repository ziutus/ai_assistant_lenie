# -*- coding: utf-8 -*-
"""Reguły czyszczenia o2.pl w data/site_rules.json (webpage_text_clean).

Przypadki oparte na dokumencie #357 (o2.pl/informacje/falszywe-ukrainki-...):
linie usunięte ręcznie podczas review są zapisane w document_removed_lines
i posłużyły do zbudowania tych reguł.
"""

import pytest

pytest.importorskip("requests")
pytest.importorskip("bs4")

from library.website.website_download_context import webpage_text_clean  # noqa: E402

O2_URL = "https://www.o2.pl/informacje/falszywe-ukrainki-zalewaja-siec-brutalny-cel-ogloszen-7250406541257024a"

HEADER = (
    "Fałszywe Ukrainki zalewają sieć. Brutalny cel ogłoszeń          "
    "ZalogujBlisko ludzio2kazjeQuizyRozrywkaPogodaBiznes"
    "Obserwuj nas na:   Fałszywe Ukrainki zalewają sieć. Brutalny cel ogłoszeń "
    "Fałszywe ogłoszenia zalewają siećŹródło zdjęć: © Facebook, Pixabay "
    "Marcin Lewicki3 lutego 2026, 13:51  Udostępnij na X  Udostępnij na Facebooku"
)

ARTICLE_P1 = "W mediach społecznościowych pojawiła się fala fałszywych ogłoszeń matrymonialnych."
ARTICLE_P2 = "Strony, do których prowadzą ogłoszenia również są fałszywe."

FOOTER = (
    "sztuczna inteligencja polska ukraina media społecznościowe +3 Wybrane dla Ciebie\n\n"
    "Wyniki Lotto 03.02.2026 – losowania Lotto\n\n"
    "Wyłączono komentarzeJako redakcja Wirtualnej Polski doceniamy zaangażowanie"
)

VIDEO_EMBED = (
    "14-latka upadła w galerii. Trafiła do szpitala. Szokujący finał\n\n"
    "NBP chce nadal zwiększać zapasy złota. Ekonomista: dziś to bardziej kontrowersyjny temat \n\n"
    "Przewiń wstecz\n\nOglądaj\n\nPrzewiń naprzód\n\nUstawienia\n\n"
    "Włącz / wyłącz pełny ekran\n\n01:49"
)


class TestO2SiteRules:
    def test_header_removed_up_to_share_buttons(self):
        text = f"{HEADER}\n\n{ARTICLE_P1}"
        result = webpage_text_clean(O2_URL, text)
        assert result == ARTICLE_P1
        assert "Zaloguj" not in result
        assert "Źródło zdjęć" not in result
        assert "Marcin Lewicki" not in result

    def test_footer_removed_from_wybrane_dla_ciebie(self):
        text = f"{ARTICLE_P2}{FOOTER}"
        result = webpage_text_clean(O2_URL, text)
        assert ARTICLE_P2.rstrip(".") in result
        assert "Wybrane dla Ciebie" not in result
        assert "Wyniki Lotto" not in result
        assert "Wyłączono komentarze" not in result
        # tagi z licznikiem "+3" doklejone do końca artykułu też znikają
        assert "sztuczna inteligencja" not in result

    def test_video_embed_with_teasers_removed(self):
        text = f"{ARTICLE_P1}\n\n{VIDEO_EMBED}\n\n{ARTICLE_P2}"
        result = webpage_text_clean(O2_URL, text)
        assert ARTICLE_P1 in result
        assert ARTICLE_P2 in result
        assert "Przewiń wstecz" not in result
        assert "Oglądaj" not in result
        assert "01:49" not in result
        assert "14-latka upadła w galerii" not in result
        assert "NBP chce nadal zwiększać" not in result

    def test_video_teaser_glued_to_paragraph_removed(self):
        # Artefakt get_text(): zajawka doklejona po kropce (dwie spacje) do końca akapitu,
        # usuwana tylko gdy dalej następuje blok playera
        glued = f'{ARTICLE_P1}  14-latka upadła w galerii. Trafiła do szpitala. Szokujący finał'
        text = f"{glued}\n\n{VIDEO_EMBED.split(chr(10) + chr(10), 2)[2]}\n\n{ARTICLE_P2}"
        result = webpage_text_clean(O2_URL, text)
        assert ARTICLE_P1 in result
        assert ARTICLE_P2 in result
        assert "14-latka" not in result

    def test_reklama_koniec_reklamy_removed(self):
        text = f"{ARTICLE_P1}REKLAMAKONIEC REKLAMY \n\n{ARTICLE_P2}\nREKLAMA\nKONIEC REKLAMY"
        result = webpage_text_clean(O2_URL, text)
        assert "REKLAMA" not in result
        assert ARTICLE_P1 in result
        assert ARTICLE_P2 in result

    def test_plain_article_untouched(self):
        text = f"{ARTICLE_P1}\n\n{ARTICLE_P2}"
        assert webpage_text_clean(O2_URL, text) == text
