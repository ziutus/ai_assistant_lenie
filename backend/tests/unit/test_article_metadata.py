"""Tests for deterministic portal metadata extraction."""

from library.article_metadata import extract_article_author, extract_article_authors


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


def test_onet_extracts_multiple_authors_from_article_json_ld():
    html = '''<script type="application/ld+json">{
      "@context": "https://schema.org", "@graph": [
        {"@type": "Person", "name": "Osoba z rekomendacji"},
        {"@type": "NewsArticle", "author": [
          {"@type": "Person", "name": "Michał Rogalski"},
          {"@type": "Person", "name": "Piotr Gruszka"}
        ]}
      ]
    }</script>'''

    assert extract_article_authors(html, "https://wiadomosci.onet.pl/artykul") == [
        "Michał Rogalski", "Piotr Gruszka",
    ]


def test_onet_does_not_collect_unrelated_people_from_json_ld_graph():
    html = '''<script type="application/ld+json">{
      "@graph": [
        {"@type": "NewsArticle", "author": {"@type": "Person", "name": "Autor Tekstu"}},
        {"@type": "Person", "name": "Autor Polecanego Tekstu"}
      ]
    }</script>'''

    assert extract_article_authors(html, "https://www.onet.pl/informacje/test") == ["Autor Tekstu"]
