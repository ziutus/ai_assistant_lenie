"""Tests for deterministic portal metadata extraction."""

from library.article_metadata import extract_article_author


def test_wp_author_prefers_cauthor_over_publisher_meta():
    html = """
    <meta name="author" content="Grupa Wirtualna Polska">
    <script>window.page={"cauthor":"Łukasz Maziewski"};</script>
    <a class="wp-article-author-link">Inna osoba</a>
    """
    assert extract_article_author(html, "https://wiadomosci.wp.pl/artykul") == "Łukasz Maziewski"


def test_wp_author_falls_back_to_visible_byline():
    html = """
    <meta name="author" content="Grupa Wirtualna Polska">
    <div id="wp-article-author-info">
      <a class="wp-article-author-link"> Łukasz Maziewski </a>
    </div>
    """
    assert extract_article_author(html, "https://tech.wp.pl/artykul") == "Łukasz Maziewski"


def test_publisher_meta_is_not_used_as_wp_author():
    html = '<meta name="author" content="Grupa Wirtualna Polska">'
    assert extract_article_author(html, "https://wiadomosci.wp.pl/artykul") is None


def test_wp_rule_does_not_apply_to_other_domains():
    html = '<script>window.page={"cauthor":"Jan Kowalski"};</script>'
    assert extract_article_author(html, "https://example.com/artykul") is None
