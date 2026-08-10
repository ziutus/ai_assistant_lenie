from library.article_metadata import extract_article_authors, extract_article_publication_date


def test_generic_jsonld_article_metadata():
    html = '''
    <html><head><script type="application/ld+json">
    {"@type":"NewsArticle","author":[{"name":"Jan Kowalski"},{"name":"Anna Nowak"}],
     "datePublished":"2026-07-21T12:30:00+02:00"}
    </script></head></html>
    '''
    assert extract_article_authors(html, "https://example.com/a") == ["Jan Kowalski", "Anna Nowak"]
    assert extract_article_publication_date(html, "https://example.com/a") == "2026-07-21"


def test_generic_meta_metadata_fallback():
    html = '''<meta name="author" content="Maria Testowa">
              <meta property="article:published_time" content="2025-03-04T08:00:00Z">'''
    assert extract_article_authors(html, "https://example.com/a") == ["Maria Testowa"]
    assert extract_article_publication_date(html, "https://example.com/a") == "2025-03-04"


def test_gazeta_pl_author_resolved_from_id_referenced_person_node():
    """gazeta.pl's NewsArticle.author is only an {"@id": ...} reference; the actual
    name lives in a separate Person node elsewhere in the same @graph (real shape
    observed on wiadomosci.gazeta.pl, doc 9376)."""
    html = '''
    <html><head><script type="application/ld+json">
    {"@context": "https://schema.org", "@graph": [
      {"@type": "BreadcrumbList"},
      {"@type": "NewsArticle",
       "author": [{"@id": "https://wiadomosci.gazeta.pl/wiadomosci/autor/60f562c447716e04bc214689"}],
       "datePublished": "2026-08-09T18:18:00+02:00"},
      {"@type": "Person",
       "@id": "https://wiadomosci.gazeta.pl/wiadomosci/autor/60f562c447716e04bc214689",
       "name": "Jakub Wencel"}
    ]}
    </script></head></html>
    '''
    assert extract_article_authors(html, "https://wiadomosci.gazeta.pl/swiat/artykul") == ["Jakub Wencel"]
    assert extract_article_publication_date(html, "https://wiadomosci.gazeta.pl/swiat/artykul") == "2026-08-09"


def test_dangling_id_reference_does_not_crash_and_yields_no_author():
    """An @id reference with no matching node in the graph must fail closed
    (no author) rather than raise — real pages can omit the Person node."""
    html = '''
    <html><head><script type="application/ld+json">
    {"@type": "NewsArticle", "author": [{"@id": "https://example.com/autor/missing"}]}
    </script></head></html>
    '''
    assert extract_article_authors(html, "https://example.com/artykul") == []


def test_inline_author_name_still_preferred_over_id_reference_in_same_list():
    html = '''
    <html><head><script type="application/ld+json">
    {"@context": "https://schema.org", "@graph": [
      {"@type": "NewsArticle", "author": [
        {"@id": "https://example.com/autor/1"},
        {"name": "Inline Autor"}
      ]},
      {"@type": "Person", "@id": "https://example.com/autor/1", "name": "Referencyjny Autor"}
    ]}
    </script></head></html>
    '''
    assert extract_article_authors(html, "https://example.com/artykul") == [
        "Referencyjny Autor", "Inline Autor",
    ]
