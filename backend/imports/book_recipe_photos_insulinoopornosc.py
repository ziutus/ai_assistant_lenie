"""Match the dish photos of "Insulinooporność. Szybkie dania" to its recipes.

Finds the full-page dish photos in the PDF, decides which recipe each one shows
(layout first, a vision model for the ambiguous ones) and either writes a contact
sheet / JSON mapping for human review (default, dry-run) or, with --apply, stores
the photos: one JPEG plus a small thumbnail per photo in object storage
(documents/<id>/images/<n>.jpg and <n>_thumb.jpg) and a `document_images` row
on the already-imported recipe Document. The licence stamp is redacted from every
rendered photo.

Recipes come from imports/book_import_recipes_insulinoopornosc.py (same parser,
same synthetic URLs), so import the recipes first.

Running:
    cd backend
    python imports/book_recipe_photos_insulinoopornosc.py book.pdf --sheet tmp/photos.html --json tmp/photos.json
    python imports/book_recipe_photos_insulinoopornosc.py book.pdf --from-json tmp/photos.json --apply
    python imports/book_recipe_photos_insulinoopornosc.py book.pdf --no-vision --limit 20

--from-json reuses a reviewed mapping instead of asking the model again; photos the
mapping left empty because of a failed model answer (confidence 0) are asked once more.
"""

import argparse
import base64
import html
import json
from collections import Counter
from concurrent.futures import ThreadPoolExecutor

from imports.book_import_recipes_insulinoopornosc import BOOK_SLUG, parse_book, recipe_url
from library.book_pdf_import import extract_pages
from library.recipe_book_parser import merge_duplicates, normalize_title
from library.recipe_book_photos import (
    PhotoMatch,
    find_photos,
    match_photo,
    recipes_by_page,
    render_photo,
    thumb_key,
)

# Human corrections for photos the model could not place, checked by eye against the page (page -> title).
PHOTO_OVERRIDES = {70: "Hummus oliwkowy"}

MAIN_DPI, MAIN_QUALITY = 150, 85
THUMB_DPI, THUMB_QUALITY = 45, 75


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


def apply_photos(doc, rows: list[dict], recipes_by_key: dict) -> None:
    """Store matched photos and link them to the imported recipe Documents."""
    from library.config_loader import load_config
    from library.db.engine import get_session
    from library.db.models import Document
    from library.document_images import replace_storage_images
    from library.storage import storage_from_config

    matched = [r for r in rows if r["recipe_key"]]
    by_recipe: dict[str, list[dict]] = {}
    for row in matched:
        by_recipe.setdefault(row["recipe_key"], []).append(row)

    storage = storage_from_config(load_config())
    photos = {p.page: p for p in find_photos(doc)}
    session = get_session()
    stored = missing = 0
    try:
        for key, recipe_rows in by_recipe.items():
            recipe = recipes_by_key[key]
            document = Document.get_by_url(session, recipe_url(recipe))
            if document is None:
                missing += 1
                print(f"  ! brak dokumentu dla przepisu: {recipe.title}")
                continue
            images = []
            for position, row in enumerate(sorted(recipe_rows, key=lambda r: r["page"])):
                photo = photos[row["page"]]
                storage_key = f"documents/{document.id}/images/{position}.jpg"
                storage.put_bytes(
                    storage_key, render_photo(doc, photo, dpi=MAIN_DPI, quality=MAIN_QUALITY), "image/jpeg"
                )
                storage.put_bytes(
                    thumb_key(storage_key), render_photo(doc, photo, dpi=THUMB_DPI, quality=THUMB_QUALITY), "image/jpeg"
                )
                images.append(
                    {
                        "storage_key": storage_key,
                        "position": None,  # shown beside the recipe, not inline in text_md
                        "page_number": photo.page,
                        "alt_text": recipe.title,
                        "caption_text": row.get("dish") or None,
                    }
                )
            replace_storage_images(session, document.id, images)
            session.commit()
            stored += len(images)
            print(f"  + {document.id}: {recipe.title} ({len(images)} zdj.)")
    finally:
        session.close()
    print(f"\nZapisano zdjec: {stored}, przepisow bez dokumentu: {missing}")


def main() -> None:
    import fitz

    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("file", help="sciezka do lokalnego pliku PDF")
    parser.add_argument("--limit", type=int, default=0, help="przetworz tylko N pierwszych zdjec (test)")
    parser.add_argument(
        "--no-vision", action="store_true", help="bez modelu wizyjnego: tylko dopasowanie z ukladu strony"
    )
    parser.add_argument("--min-confidence", type=float, default=0.85, help="prog pewnosci modelu wizyjnego")
    parser.add_argument("--sheet", metavar="PLIK", help="arkusz kontaktowy HTML")
    parser.add_argument("--json", metavar="PLIK", help="mapowanie zdjecie -> przepis jako JSON")
    parser.add_argument("--from-json", metavar="PLIK", help="uzyj zatwierdzonego mapowania zamiast pytac model")
    parser.add_argument("--apply", action="store_true", help="zapisz zdjecia do storage i bazy (domyslnie dry-run)")
    args = parser.parse_args()

    with open(args.file, "rb") as fh:
        data = fh.read()
    pages = extract_pages(data)
    occurrences = parse_book(pages)
    recipes_by_key = {r.key: r for r in merge_duplicates(list(occurrences))}
    titles = {key: r.title for key, r in recipes_by_key.items()}
    index = recipes_by_page(occurrences)

    doc = fitz.open(stream=data, filetype="pdf")
    photos = find_photos(doc)
    if args.limit:
        photos = photos[: args.limit]
    kwargs = {"min_confidence": args.min_confidence}
    if args.no_vision:
        kwargs["vision"] = _no_vision

    saved = {}
    if args.from_json:
        with open(args.from_json, encoding="utf-8") as fh:
            saved = {row["page"]: row for row in json.load(fh)}

    # fitz is not thread-safe: render first, then ask the model concurrently.
    def needs_model(photo) -> bool:
        row = saved.get(photo.page)
        return row is None or (not row["recipe_key"] and row["confidence"] == 0 and bool(row["candidates"]))

    smalls = {p.page: render_photo(doc, p, dpi=100, quality=75) for p in photos if needs_model(p)}
    thumbs = {p.page: render_photo(doc, p, dpi=40, quality=70) for p in photos} if args.sheet else {}

    def decide(photo) -> PhotoMatch:
        override = normalize_title(PHOTO_OVERRIDES[photo.page]) if photo.page in PHOTO_OVERRIDES else None
        if override in recipes_by_key:
            return PhotoMatch(photo, override, "manual", 1.0, [], None)
        if needs_model(photo):
            return match_photo(photo, smalls[photo.page], index, **kwargs)
        row = saved[photo.page]
        return PhotoMatch(photo, row["recipe_key"], row["method"], row["confidence"], [], row.get("dish"))

    with ThreadPoolExecutor(max_workers=4) as pool:
        matches = list(pool.map(decide, photos))

    rows = []
    for photo, match in zip(photos, matches):
        candidates = (
            [titles[k] for k in match.candidates]
            if match.candidates
            else saved.get(photo.page, {}).get("candidates", [])
        )
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
                "candidates": candidates,
                "thumb": base64.b64encode(thumbs[photo.page]).decode("ascii") if thumbs else "",
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
    if args.apply:
        print(f"\nZapis zdjec ({BOOK_SLUG}) do storage i bazy:")
        apply_photos(doc, rows, recipes_by_key)
    else:
        print("\nDry-run — nic nie zapisano do bazy ani do storage. Uzyj --apply.")


if __name__ == "__main__":
    main()
