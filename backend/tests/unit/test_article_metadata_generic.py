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
