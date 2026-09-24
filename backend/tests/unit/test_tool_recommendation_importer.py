from library.tool_recommendation_importer import github_raw_url, parse_markdown_recommendations


def test_repository_url_becomes_raw_readme_url():
    assert github_raw_url("https://github.com/AwesomeHomelab/awesome-homelab") == (
        "https://raw.githubusercontent.com/AwesomeHomelab/awesome-homelab/HEAD/README.md"
    )


def test_parser_preserves_category_description_and_ignores_heading_row():
    markdown = """## Apps
### Bookmarking
| Name | Info | Description |
| --- | --- | --- |
| [LinkStack](https://github.com/LinkStackOrg/linkstack-docker) | stars | Link sharing platform |
"""
    assert parse_markdown_recommendations(markdown) == [{
        "name": "LinkStack",
        "homepage_url": "https://github.com/LinkStackOrg/linkstack-docker",
        "description": "Link sharing platform",
        "category": "Bookmarking",
    }]


def test_raw_githubusercontent_url_is_rebuilt_from_validated_parts():
    assert github_raw_url("https://raw.githubusercontent.com/o/r/main/README.md") == (
        "https://raw.githubusercontent.com/o/r/main/README.md"
    )


def test_non_github_hosts_are_rejected():
    import pytest

    for url in ("https://evilgithub.com/o/r", "http://github.com/o/r", "https://github.com.evil.io/o/r"):
        with pytest.raises(ValueError):
            github_raw_url(url)


def test_parser_is_linear_on_unclosed_brackets():
    import time

    start = time.monotonic()
    parse_markdown_recommendations("| " + "[" * 50000 + " |\n## " + "x " * 50000)
    assert time.monotonic() - start < 2
