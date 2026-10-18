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
    python imports/book_import_recipes_insulinoopornosc.py book.pdf --apply          # one Document per recipe
    python imports/book_import_recipes_insulinoopornosc.py book.pdf --apply --embed  # + embeddings (needs config)

Data access: ORM (SQLAlchemy) via get_session(), only when --apply is passed.
Re-running is safe: a recipe whose synthetic URL already exists is skipped.
"""

import argparse
import difflib
import sys

from library.book_pdf_import import extract_pages, slugify
from library.recipe_book_parser import (
    merge_duplicates,
    parse_index,
    parse_recipes,
    recipe_tags,
    recipe_to_markdown,
)

BOOK_TITLE = "Insulinooporność. Szybkie dania"
BYLINE = "Magdalena Makarowska, Dominika Musiałowska"
BOOK_SLUG = "insulinoopornosc-szybkie-dania"
BASE_TAGS = ("przepis", "insulinooporność", "szybkie-dania")

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


def recipe_url(recipe) -> str:
    """Synthetic, stable identity (mirrors file:///ksiazki/<slug>.pdf for whole books)."""
    return f"file:///ksiazki/{BOOK_SLUG}/{slugify(recipe.title)}"


def apply_import(recipes, *, source: str, embed: bool) -> None:
    """Create one `text` Document per recipe; skip those already imported."""
    from library.db.engine import get_session
    from library.document_service import DocumentService, ExistingDocumentError

    session = get_session()
    created = skipped = embedded = 0
    try:
        service = DocumentService(session)
        repo = model = None
        if embed:
            import library.embedding as embedding
            from library.config_loader import load_config
            from library.document_repository import DocumentRepository
            from library.obsidian_reimport_service import _embedding_parts

            model = load_config().require("EMBEDDING_MODEL")
            repo = DocumentRepository(session)
        for recipe in recipes:
            pages = ", ".join(str(page) for page in sorted(recipe.pages))
            try:
                doc = service.create_document(
                    url=recipe_url(recipe),
                    url_type="text",
                    title=recipe.title,
                    note=f"Książka „{BOOK_TITLE}”, s. {pages}",
                    source=source,
                    language="pl",
                )
            except ExistingDocumentError:
                skipped += 1
                continue
            markdown = recipe_to_markdown(recipe)
            doc.byline = BYLINE
            doc.text_md = markdown
            doc.text = markdown
            doc.tags = ",".join(recipe_tags(recipe, BASE_TAGS))
            session.commit()
            created += 1
            if embed:
                for part in _embedding_parts(markdown):
                    result = embedding.get_embedding(model=model, text=part)
                    if result.status != "success" or not result.embedding:
                        raise RuntimeError(f"Embedding failed for document {doc.id}: {result.status}")
                    repo.embedding_add(doc.id, result.embedding, "pl", part, part, model)
                session.commit()
                embedded += 1
            print(f"  + {doc.id}: {recipe.title}")
    finally:
        session.close()
    print(f"\nUtworzono: {created}, pominieto (juz istnieja): {skipped}, z embeddingami: {embedded}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("file", help="sciezka do lokalnego pliku PDF")
    parser.add_argument("--show", type=int, default=0, metavar="N", help="pokaz N pierwszych przepisow jako markdown")
    parser.add_argument("--dump", metavar="PLIK", help="zapisz wszystkie przepisy jako markdown do pliku")
    parser.add_argument("--apply", action="store_true", help="zapisz do bazy (domyslnie dry-run)")
    parser.add_argument(
        "--embed", action="store_true", help="z --apply: wygeneruj tez embeddingi (wymaga konfiguracji)"
    )
    parser.add_argument("--source", default="książka", help="zrodlo odkrycia (domyslnie 'książka')")
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
    if not unique:
        sys.exit(1)
    if args.apply:
        print()
        apply_import(unique, source=args.source, embed=args.embed)
    else:
        print("\nDry-run — nic nie zapisano do bazy. Uzyj --apply.")


if __name__ == "__main__":
    main()
