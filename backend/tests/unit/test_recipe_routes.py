import pytest

pytest.importorskip("flask")
pytest.importorskip("sqlalchemy")

from library.recipe_book_parser import Recipe, recipe_to_markdown  # noqa: E402
from library.recipe_routes import parse_recipe_markdown, split_tags  # noqa: E402


def test_split_tags_handles_empty_and_spaces():
    assert split_tags(None) == []
    assert split_tags("przepis, obiad ,wege,") == ["przepis", "obiad", "wege"]


def test_parse_round_trips_rendered_recipe():
    recipe = Recipe(
        title="Sernik",
        servings="ok. 10",
        nutrition="w porcji ok. 135 kcal, B 12 g/T 5 g/W 12 g",
        notes=["Schłodź przed podaniem."],
        ingredients=["**spód**", "3 żółtka", "160 g fasoli", "**masa**", "400 g sera"],
        method="Zmiksuj.\n\nPiecz 45 minut.",
        occurrences=[{"month": 1, "week": 2, "day": "środa", "meal": "obiad", "page": 100}],
    )
    parsed = parse_recipe_markdown(recipe_to_markdown(recipe))
    assert parsed["servings"] == "ok. 10"
    assert parsed["meals"] == ["obiad"]
    assert parsed["nutrition"] == "w porcji ok. 135 kcal, B 12 g/T 5 g/W 12 g"
    assert parsed["notes"] == ["Schłodź przed podaniem."]
    assert parsed["ingredients"] == [
        {"text": "spód", "label": True},
        {"text": "3 żółtka", "label": False},
        {"text": "160 g fasoli", "label": False},
        {"text": "masa", "label": True},
        {"text": "400 g sera", "label": False},
    ]
    assert parsed["method"] == ["Zmiksuj.", "Piecz 45 minut."]
    assert parsed["menu_slots"] == ["miesiąc I, tydzień 2, środa, obiad"]


def test_parse_empty_text():
    parsed = parse_recipe_markdown(None)
    assert parsed["ingredients"] == [] and parsed["method"] == [] and parsed["servings"] is None
