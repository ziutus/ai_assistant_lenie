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
