"""Match the dish photos of "Insulinooporność. Szybkie dania" to its recipes.

Dry-run only for now: finds the photos in the PDF, decides which recipe each
shows (layout first, a vision model for the ambiguous ones) and writes a contact
sheet (HTML with thumbnails) plus a JSON mapping for human review. Nothing is
written to the database or object storage.

Recipes come from imports/book_import_recipes_insulinoopornosc.py (same parser),
so the keys here are the same normalised titles the imported Documents use.

Running:
    cd backend
    python imports/book_recipe_photos_insulinoopornosc.py book.pdf --sheet tmp/photos.html --json tmp/photos.json
    python imports/book_recipe_photos_insulinoopornosc.py book.pdf --no-vision --limit 20
"""

import argparse
import base64
import html
import json
from collections import Counter
from concurrent.futures import ThreadPoolExecutor

from imports.book_import_recipes_insulinoopornosc import parse_book
from library.book_pdf_import import extract_pages
from library.recipe_book_parser import merge_duplicates
from library.recipe_book_photos import (
    find_photos,
    match_photo,
    recipes_by_page,
    render_photo,
)


def _no_vision(_jpeg, _titles):
    return None, 0.0, ""


def write_sheet(path: str, rows: list[dict]) -> None:
    cards = []
    for row in rows:
        status = row["method"] if row["recipe"] else "BRAK"
        color = {"sole": "#dcfce7", "vision": "#dbeafe", "BRAK": "#fee2e2"}.get(status, "#eee")
        alternatives = "".join(f"<li>{html.escape(t)}</li>" for t in row["candidates"])
        cards.append(
            f'<div class="c" style="background:{color}"><img src="data:image/jpeg;base64,{row["thumb"]}">'
            f"<b>{html.escape(row['recipe'] or '— bez przypisania —')}</b>"
            f"<small>s. {row['page']} · {status} · {row['confidence']:.2f}"
            f"{' · cała strona' if row['full_page'] else ''}</small>"
            f"<small>{html.escape(row['dish'] or '')}</small>"
            f"<details><summary>kandydaci ({len(row['candidates'])})</summary><ul>{alternatives}</ul></details></div>"
        )
    document = (
        '<meta charset="utf-8"><title>Zdjęcia → przepisy</title>'
        "<style>body{font:14px system-ui;margin:12px}.g{display:grid;grid-template-columns:repeat(auto-fill,minmax(230px,1fr));gap:10px}"
        ".c{padding:8px;border-radius:8px;display:flex;flex-direction:column;gap:3px}img{width:100%;border-radius:4px}"
        "small{color:#445}ul{margin:4px 0;padding-left:16px}</style>"
        f"<h2>Zdjęcia → przepisy ({len(rows)})</h2><div class='g'>{''.join(cards)}</div>"
    )
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(document)


def main() -> None:
    import fitz

    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("file", help="sciezka do lokalnego pliku PDF")
    parser.add_argument("--limit", type=int, default=0, help="przetworz tylko N pierwszych zdjec (test)")
    parser.add_argument(
        "--no-vision", action="store_true", help="bez modelu wizyjnego: tylko dopasowanie z ukladu strony"
    )
    parser.add_argument("--min-confidence", type=float, default=0.6, help="prog pewnosci modelu wizyjnego")
    parser.add_argument("--sheet", metavar="PLIK", help="arkusz kontaktowy HTML")
    parser.add_argument("--json", metavar="PLIK", help="mapowanie zdjecie -> przepis jako JSON")
    args = parser.parse_args()

    with open(args.file, "rb") as fh:
        data = fh.read()
    pages = extract_pages(data)
    occurrences = parse_book(pages)
    titles = {r.key: r.title for r in merge_duplicates(list(occurrences))}
    index = recipes_by_page(occurrences)

    doc = fitz.open(stream=data, filetype="pdf")
    photos = find_photos(doc)
    if args.limit:
        photos = photos[: args.limit]
    vision = _no_vision if args.no_vision else None

    # fitz is not thread-safe: render everything first, then ask the model concurrently.
    renders = [(render_photo(doc, p, dpi=100, quality=75), render_photo(doc, p, dpi=40, quality=70)) for p in photos]
    kwargs = {"min_confidence": args.min_confidence}
    if vision:
        kwargs["vision"] = vision
    with ThreadPoolExecutor(max_workers=4) as pool:
        matches = list(pool.map(lambda pr: match_photo(pr[0], pr[1][0], index, **kwargs), zip(photos, renders)))

    rows = []
    for photo, match, (_small, thumb) in zip(photos, matches, renders):
        rows.append(
            {
                "index": photo.index,
                "page": photo.page,
                "full_page": photo.full_page,
                "rect": [round(v, 1) for v in photo.rect],
                "recipe_key": match.recipe_key,
                "recipe": titles.get(match.recipe_key),
                "method": match.method,
                "confidence": match.confidence,
                "dish": match.dish,
                "candidates": [titles[k] for k in match.candidates],
                "thumb": base64.b64encode(thumb).decode("ascii"),
            }
        )

    methods = Counter((r["method"] if r["recipe"] else "bez przypisania") for r in rows)
    per_recipe = Counter(r["recipe_key"] for r in rows if r["recipe_key"])
    print(f"Zdjec: {len(rows)} (cala strona: {sum(r['full_page'] for r in rows)})")
    print("Przypisanie:", dict(methods))
    print(
        f"Przepisow ze zdjeciem: {len(per_recipe)} z {len(titles)}; ze zdjeciami >1: {sum(c > 1 for c in per_recipe.values())}"
    )
    if args.sheet:
        write_sheet(args.sheet, rows)
        print(f"Arkusz: {args.sheet}")
    if args.json:
        with open(args.json, "w", encoding="utf-8") as fh:
            json.dump([{k: v for k, v in r.items() if k != "thumb"} for r in rows], fh, ensure_ascii=False, indent=1)
        print(f"JSON: {args.json}")
    print("\nDry-run — nic nie zapisano do bazy ani do storage.")


if __name__ == "__main__":
    main()
