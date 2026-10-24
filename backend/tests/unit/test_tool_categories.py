import pytest

from library.tool_categories import canonical_category
from library.tool_recommendation_importer import parse_markdown_recommendations


@pytest.mark.parametrize("raw, expected", [
    ("security", "Security"),
    ("Security", "Security"),
    ("decision-models", "DecisionModels"),
    ("Decision Models", "DecisionModels"),
    ("infrastructure", "InfraManagement"),
    ("notes", "Notatki i produktywność"),
    ("  Monitoring  ", "Monitoring"),
    ("Bezpieczeństwo i certyfikaty", "Bezpieczeństwo i certyfikaty"),
    ("", None),
    (None, None),
])
def test_canonical_category(raw, expected):
    assert canonical_category(raw) == expected


def test_import_headings_use_the_canonical_spelling():
    markdown = "## security\n| Name | Description |\n|---|---|\n| [Vault](https://vaultproject.io) | Secrets |\n"
    items = parse_markdown_recommendations(markdown)
    assert items and all(item["category"] == "Security" for item in items)
