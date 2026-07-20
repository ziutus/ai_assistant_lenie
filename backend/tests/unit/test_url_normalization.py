import pytest

from library.url_normalization import canonicalize_url


@pytest.mark.parametrize(("raw", "expected"), [
    (
        " HTTPS://Example.COM:443/article/?b=2&utm_source=x&a=1#section ",
        "https://example.com/article?a=1&b=2",
    ),
    ("https://example.com", "https://example.com/"),
    ("http://example.com:80/a/", "http://example.com/a"),
    ("legacy/path/?utm_source=x#part", "legacy/path"),
    ("https://example.com/a?id=7&ref=home", "https://example.com/a?id=7&ref=home"),
    ("https://youtu.be/abc123?t=20", "https://www.youtube.com/watch?v=abc123"),
    (
        "https://m.youtube.com/watch?feature=share&v=abc123&utm_medium=x",
        "https://www.youtube.com/watch?v=abc123",
    ),
])
def test_canonicalize_url(raw, expected):
    assert canonicalize_url(raw) == expected


def test_blank_url_is_rejected():
    with pytest.raises(ValueError, match="empty"):
        canonicalize_url("  ")
