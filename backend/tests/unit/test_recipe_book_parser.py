from library.recipe_book_parser import (
    clean_page_text,
    merge_duplicates,
    normalize_title,
    parse_index,
    parse_recipes,
    recipe_to_markdown,
)

WATERMARK = "ebookpoint kopia dla: Jan Kowalski jan@example.com G123\n00ff8b013177187aaf6f751e785328f6"


def _page(number: int, body: str) -> str:
    return f"{number}\n{body}\n{WATERMARK}\n"


def test_clean_page_text_drops_watermark_and_soft_hyphens():
    text = clean_page_text(f"gło\xad\nwie i dalej\n{WATERMARK}\n")
    assert "ebookpoint" not in text
    assert "00ff8b" not in text
    assert "głowie i dalej" in text


def test_meal_plan_recipe_with_wrapped_portions_line():
    pages = [
        _page(
            1,
            "poniedziałek – wtorek\n"
            "obiad: Filet w sezamie z pęczakiem\n– 2 porcje\n"
            "* Dzieci chętnie zjedzą :)\n"
            "• 300 g mięsa z drobiu lub W WERSJI WEGE bakłażana\n"
            "• 130 g kaszy pęczak (namoczonej\n"
            "na noc)\n"
            "• dodatki: 2 łyżki oliwy\n"
            "Mięso pokrój w plastry. Kaszę ugotuj al dente.\n"
            "podwieczorek: Surówka z kapusty – 1 porcja\n"
            "• 200 g kapusty\n"
            "Wymieszaj.\n",
        )
    ]
    recipes = parse_recipes(pages, 1, 1, context_for_page=lambda page: {"month": 1, "week": 2})
    assert [r.title for r in recipes] == ["Filet w sezamie z pęczakiem", "Surówka z kapusty"]
    first = recipes[0]
    assert first.meal == "obiad"
    assert first.servings == "2"
    assert first.notes == ["Dzieci chętnie zjedzą :)"]
    assert first.ingredients[1] == "130 g kaszy pęczak (namoczonej na noc)"
    assert first.method == "Mięso pokrój w plastry. Kaszę ugotuj al dente."
    assert first.occurrences[0] == {"month": 1, "week": 2, "day": "poniedziałek – wtorek", "meal": "obiad", "page": 1}
    assert "ebookpoint" not in recipe_to_markdown(first)


def test_plain_titles_and_section_banner_not_attached_as_method():
    pages = [
        _page(
            1,
            "Guacamole\n• 1 awokado\n• 1 cytryna\nZgnieć widelcem.\n"
            "Zdrowe pieczywo\n"
            "Placki gryczane\n• ½ szklanki mąki\nSmaż po 3 minuty.\n",
        )
    ]
    recipes = parse_recipes(pages, 1, 1)
    assert [r.title for r in recipes] == ["Guacamole", "Placki gryczane"]
    assert recipes[0].method == "Zgnieć widelcem."
    assert recipes[1].section == "Zdrowe pieczywo"


def test_month_banner_is_not_a_section():
    pages = [
        _page(
            1,
            "Zupa – 2 porcje\n• 1 marchew\nUgotuj.\nII MIESIĄC\nI TYDZIEŃ\nKolejna zupa – 1 porcja\n• 1 seler\nGotuj.\n",
        )
    ]
    recipes = parse_recipes(pages, 1, 1)
    assert recipes[1].section is None
    assert recipes[0].method == "Ugotuj."


def test_labelled_sub_blocks_keep_the_whole_method():
    pages = [
        _page(
            1,
            "Sernik – ok. 10 porcji\n(w porcji ok. 135 kcal, B 12 g/T 5 g/W 12 g)\n"
            "spód\n• 3 żółtka\n• 160 g fasoli\n"
            "Fasolę zmiksuj z żółtkami.\n"
            "masa sernikowa\n• 400 g sera\n• 3 białka\n"
            "Wlej masę na spód.\n",
        )
    ]
    (recipe,) = parse_recipes(pages, 1, 1)
    assert recipe.servings == "ok. 10"
    assert recipe.nutrition.startswith("w porcji ok. 135 kcal")
    assert recipe.ingredients == [
        "**spód**",
        "3 żółtka",
        "160 g fasoli",
        "**masa sernikowa**",
        "400 g sera",
        "3 białka",
    ]
    assert "Fasolę zmiksuj" in recipe.method and "Wlej masę" in recipe.method


def test_vege_variant_line_is_not_a_title():
    pages = [_page(1, "Sałatka – 2 porcje\n• 100 g sera\nPokrój.\nWEGE wędzonego tofu\n• 50 g tofu\nDodaj tofu.\n")]
    recipes = parse_recipes(pages, 1, 1)
    assert [r.title for r in recipes] == ["Sałatka"]


def test_volume_suffix_becomes_servings():
    pages = [_page(1, "podwieczorek: Koktajl piernikowy 300 ml\n• 200 ml kefiru\nZmiksuj.\n")]
    (recipe,) = parse_recipes(pages, 1, 1)
    assert recipe.title == "Koktajl piernikowy"
    assert recipe.servings == "300 ml"


def test_merge_duplicates_keeps_every_occurrence():
    pages = [
        _page(1, "obiad: Zupa – 2 porcje\n• 1 marchew\nUgotuj.\n"),
        _page(2, "kolacja: Zupa – 2 porcje\n• 1 marchew\n• 1 seler\nUgotuj i podaj.\n"),
    ]
    recipes = parse_recipes(pages, 1, 2, context_for_page=lambda p: {"month": 1, "week": p})
    (merged,) = merge_duplicates(recipes)
    assert len(merged.occurrences) == 2
    assert merged.pages == [1, 2]
    assert merged.ingredients == ["1 marchew", "1 seler"]  # the fuller version wins


def test_prose_box_after_last_recipe_is_not_method():
    pages = [
        _page(
            1,
            "Pasta – 1 porcja\n• 1 fasola\nZmiksuj.\nPrzepisy na obiad i kolację zawierają 5 składników.\nInne zdanie.\n",
        )
    ]
    (recipe,) = parse_recipes(pages, 1, 1)
    assert recipe.method == "Zmiksuj."


def test_parse_index_joins_wrapped_entries():
    pages = [
        _page(
            1,
            "Indeks przepisów Guacamole 62\n"
            "Ciasto obłędnie czekoladowo-\n-karmelowe 261\n"
            "Burgery na kolorowo z warzywami i kaszą\ngryczaną 173\n",
        )
    ]
    index = parse_index(pages, 1, 1)
    assert index[normalize_title("Guacamole")] == 62
    assert index[normalize_title("Ciasto obłędnie czekoladowo-karmelowe")] == 261
    assert index[normalize_title("Burgery na kolorowo z warzywami i kaszą gryczaną")] == 173
