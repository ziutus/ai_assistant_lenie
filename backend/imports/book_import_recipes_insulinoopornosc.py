"""CLI wrapper for importing the recipes of "Insulinooporność. Szybkie dania"
(M. Makarowska, D. Musiałowska, ebookpoint) as one Document per recipe.

Thin on purpose — the parsing lives in library/recipe_book_parser.py (pure
functions, reusable from a worker). This file holds only the book's own layout
constants: which printed pages hold recipes, where each month/week of the meal
plan starts, and where the printed "Indeks przepisów" is.

Run imports/check_pdf_text_layer.py first — this script assumes a text layer.

Running:
    cd backend
    python imports/book_import_recipes_insulinoopornosc.py book.pdf                  # dry-run summary
    python imports/book_import_recipes_insulinoopornosc.py book.pdf --show 5         # + 5 rendered recipes
    python imports/book_import_recipes_insulinoopornosc.py book.pdf --dump out.md    # all recipes to a file
"""

import argparse
import difflib
import sys

from library.book_pdf_import import extract_pages
from library.recipe_book_parser import (
    merge_duplicates,
    parse_index,
    parse_recipes,
    recipe_to_markdown,
)

# Printed page == PDF page number (verified on the ebookpoint edition).
BASIC_RECIPE_PAGES = (62, 80)  # rozdział 4: pasty, pieczywo, mięsa, sałatki
MEAL_PLAN_PAGES = (87, 258)  # jadłospisy: 3 miesiące x 4 tygodnie
SWEETS_PAGES = (259, 273)  # "Na słodko"
INDEX_PAGES = (301, 305)  # "Indeks przepisów"

# First page of each week of the meal plan ("Spis treści"): month, week.
_WEEK_STARTS = [
    (87, 1, 1),
    (100, 1, 2),
    (111, 1, 3),
    (127, 1, 4),
    (142, 2, 1),
    (155, 2, 2),
    (170, 2, 3),
    (189, 2, 4),
    (203, 3, 1),
    (214, 3, 2),
    (230, 3, 3),
    (244, 3, 4),
]


def plan_context(page: int) -> dict:
    """Month/week of a meal-plan page; empty for pages outside the plan."""
    if not MEAL_PLAN_PAGES[0] <= page <= MEAL_PLAN_PAGES[1]:
        return {}
    context: dict = {}
    for start, month, week in _WEEK_STARTS:
        if page >= start:
            context = {"month": month, "week": week}
    return context


def parse_book(pages: list[str]):
    """All recipes of the book in reading order, duplicates not yet merged."""
    recipes = []
    recipes += parse_recipes(pages, *BASIC_RECIPE_PAGES)
    recipes += parse_recipes(pages, *MEAL_PLAN_PAGES, context_for_page=plan_context)
    recipes += parse_recipes(pages, *SWEETS_PAGES)
    return recipes


def _has_close(key: str, candidates: set[str], cutoff: float = 0.85) -> bool:
    """The book's index and headings spell some titles differently ("chili"/"chilli")."""
    return key in candidates or bool(difflib.get_close_matches(key, list(candidates), n=1, cutoff=cutoff))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("file", help="sciezka do lokalnego pliku PDF")
    parser.add_argument("--show", type=int, default=0, metavar="N", help="pokaz N pierwszych przepisow jako markdown")
    parser.add_argument("--dump", metavar="PLIK", help="zapisz wszystkie przepisy jako markdown do pliku")
    args = parser.parse_args()

    with open(args.file, "rb") as fh:
        pages = extract_pages(fh.read())

    everything = parse_book(pages)
    unique = merge_duplicates(everything)
    index = parse_index(pages, *INDEX_PAGES)

    found = {recipe.key for recipe in unique}
    missing = sorted(k for k in index if not _has_close(k, found))
    extra = sorted(k for k in found if not _has_close(k, set(index)))

    print(f"Plik: {args.file} ({len(pages)} stron)")
    print(f"Przepisow w tekscie (z powtorzeniami): {len(everything)}")
    print(f"Unikalnych przepisow: {len(unique)}")
    print(f"Wpisow w indeksie ksiazki: {len(index)}")
    print(f"  z indeksu, nieznalezione w tekscie: {len(missing)}")
    print(f"  w tekscie, brak w indeksie: {len(extra)}")
    no_method = [r.title for r in unique if not r.method]
    no_ingredients = [r.title for r in unique if not r.ingredients]
    print(f"Bez opisu przygotowania: {len(no_method)}; bez skladnikow: {len(no_ingredients)}")
    for label, titles in (("Brak w tekscie", missing), ("Brak w indeksie", extra), ("Bez przygotowania", no_method)):
        if titles:
            print(f"\n{label}:")
            for title in titles[:40]:
                print(f"  - {title}")

    if args.show:
        print()
        for recipe in unique[: args.show]:
            print("=" * 70)
            print(recipe_to_markdown(recipe))
            print(f"[strony: {recipe.pages}; wystapien: {len(recipe.occurrences)}]")
    if args.dump:
        with open(args.dump, "w", encoding="utf-8") as out:
            for recipe in unique:
                out.write(recipe_to_markdown(recipe))
                out.write(f"\n\n_Strony: {recipe.pages}; wystąpienia: {recipe.occurrences}_\n\n---\n\n")
        print(f"\nZapisano {len(unique)} przepisow do {args.dump}")
    print("\nDry-run — nic nie zapisano do bazy.")
    if not unique:
        sys.exit(1)


if __name__ == "__main__":
    main()
