# -*- coding: utf-8 -*-
"""Reguły czyszczenia o2.pl w data/site_rules.json (webpage_text_clean).

Przypadki oparte na dokumencie #357 (o2.pl/informacje/falszywe-ukrainki-...):
linie usunięte ręcznie podczas review są zapisane w document_removed_lines
i posłużyły do zbudowania tych reguł.
"""

import json
import logging

import pytest

pytest.importorskip("requests")
pytest.importorskip("bs4")

from library.website import website_download_context  # noqa: E402
from library.website.website_download_context import load_site_rules, webpage_text_clean  # noqa: E402

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


@pytest.fixture(autouse=True)
def default_site_rules_config(monkeypatch):
    monkeypatch.setattr(
        website_download_context,
        "load_config",
        lambda: {"SITE_RULES_PATH": "data/site_rules.json"},
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


def test_site_rules_path_is_configurable(monkeypatch, tmp_path):
    rules_path = tmp_path / "site-rules.json"
    rules_path.write_text(json.dumps({"example.com": {
        "remove_before": [],
        "remove_after": [],
        "remove_string": ["REMOVE ME"],
        "remove_string_regexp": [],
    }}), encoding="utf-8")
    monkeypatch.setattr(
        website_download_context,
        "load_config",
        lambda: {"SITE_RULES_PATH": str(rules_path)},
    )

    assert webpage_text_clean("https://example.com/article", "keep REMOVE ME this") == "keep  this"


@pytest.mark.parametrize(
    ("url", "artifact"),
    [
        ("https://www.money.pl/artykul", "25 komentarzy\nSłuchaj\nUdostępnij na Facebooku Udostępnij na X Udostępnij na WhatsApp Kopiuj link"),
        ("https://www.onet.pl/informacje/test", "Zapytaj o więcej Onet Czat z AI [link0]\nWięcej pogłębionych treści\nWięcej treści premium dla Ciebie\nDalszy ciąg artykułu pod materiałem wideo"),
        ("https://businessinsider.com.pl/test", "Dalszy ciąg artykułu pod materiałem wideo\n**Zobacz także:** **Polecany tekst** [link0]\n|"),
        ("https://ithardware.pl/test", "Dalsza część artykulu pod video\nPlay\nad"),
    ],
)
def test_domain_safe_ui_artifacts_removed(url, artifact):
    article = "To jest zwykła treść artykułu, która ma pozostać bez zmian."
    result = webpage_text_clean(url, f"{artifact}\n{article}")
    assert result == article


def test_tech_wp_newsletter_removed_without_matching_article_phrase():
    newsletter = (
        "PREMIUM Zapisz się na newsletter!\n"
        "Newsy, wywiady, śledztwa i reportaże w Twojej skrzynce co tydzień - zawsze za darmo.\n"
        "Zapisz mnie"
    )
    article = "Zapisz mnie na listę uczestników spotkania."
    result = webpage_text_clean("https://tech.wp.pl/test", f"{newsletter}\n{article}")
    assert result == article


def test_gazeta_gallery_controls_removed_without_touching_article_sentence():
    controls = (
        "Otwórz galerię (3)\n"
        "[przejdź na](https://www.gazeta.pl/0%2C0.html?utm_campaign=test)"
    )
    article = "Czytelnik może przejść na wystawę i otworzyć galerię sztuki."
    result = webpage_text_clean(
        "https://wiadomosci.gazeta.pl/swiat/test",
        f"{controls}\n{article}",
    )
    assert result == article


def test_global_two_line_ad_marker_removed_between_article_paragraphs():
    before = "Akapit przed reklamą pozostaje."
    after = "Akapit po reklamie pozostaje."
    result = webpage_text_clean(
        "https://example.com/article",
        f"{before}\nREKLAMA\nKONIEC REKLAMY\n{after}",
    )
    assert result == f"{before}\n\n{after}"


@pytest.mark.parametrize("url", ["https://www.money.pl/test", "https://wiadomosci.wp.pl/test"])
def test_wp_platform_glued_author_email_removed_but_normal_email_kept(url):
    artifact = "jan.kowalski@grupawp.plo autorze"
    article = "Kontakt pod adresem redakcja@grupawp.pl pozostaje częścią tekstu."
    assert webpage_text_clean(url, f"{artifact}\n{article}") == article


@pytest.mark.parametrize("contents", [None, "not valid json"])
def test_missing_or_invalid_rules_fall_back_to_empty_rules(tmp_path, caplog, contents):
    rules_path = tmp_path / "site-rules.json"
    if contents is not None:
        rules_path.write_text(contents, encoding="utf-8")

    with caplog.at_level(logging.WARNING, logger=website_download_context.__name__):
        assert load_site_rules(str(rules_path)) == {}

    assert "Cannot load site cleanup rules" in caplog.text
