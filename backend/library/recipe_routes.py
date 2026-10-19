"""Flask blueprint: recipes imported from cookbooks (documents tagged `przepis`).

Endpoints (x-api-key required via the global before_request):
  GET /recipes       — paginated list (limit/offset/total); filters: q, meal, wege;
                       also returns per-meal counts for the filter chips
  GET /recipes/<id>  — one recipe split into ingredients / method / meal-plan slots

A recipe is an ordinary `text` Document whose `text_md` was rendered by
``library.recipe_book_parser.recipe_to_markdown()``; this module only reads it
back (no extra table), so the document keeps working in /list, /read and search.
"""

import re

from flask import Blueprint, jsonify, request
from sqlalchemy import func, select

import logging

from library.db.engine import get_scoped_session
from library.db.models import Document, DocumentImage
from library.recipe_book_photos import thumb_key

logger = logging.getLogger(__name__)

bp = Blueprint("recipes", __name__)

RECIPE_TAG = "przepis"
MEAL_TAGS = {
    "śniadanie": "Śniadanie",
    "drugie-śniadanie": "II śniadanie",
    "obiad": "Obiad",
    "podwieczorek": "Podwieczorek",
    "kolacja": "Kolacja",
}
WEGE_TAG = "wege"
_TAG_RE = r"(^|,)%s(,|$)"


def split_tags(raw: str | None) -> list[str]:
    return [tag.strip() for tag in (raw or "").split(",") if tag.strip()]


def parse_recipe_markdown(text_md: str | None) -> dict:
    """Split the markdown rendered by recipe_to_markdown() back into fields."""
    recipe: dict = {
        "servings": None,
        "meals": [],
        "section": None,
        "nutrition": None,
        "notes": [],
        "ingredients": [],
        "method": [],
        "menu_slots": [],
    }
    section = "head"
    paragraph: list[str] = []

    def flush_paragraph() -> None:
        if paragraph:
            text = " ".join(paragraph).strip()
            if section == "method":
                recipe["method"].append(text)
            paragraph.clear()

    for raw in (text_md or "").splitlines():
        line = raw.rstrip()
        if line.startswith("# "):
            continue
        if line.startswith("## "):
            flush_paragraph()
            heading = line[3:].strip()
            section = {"Składniki": "ingredients", "Przygotowanie": "method", "W jadłospisie": "menu"}.get(
                heading, "other"
            )
            continue
        if not line:
            flush_paragraph()
            continue
        if section == "head":
            if line.startswith(">"):
                recipe["notes"].append(line.lstrip("> ").strip())
            elif line.startswith("_") and line.endswith("_"):
                recipe["nutrition"] = line.strip("_")
            else:
                for part in line.split(" · "):
                    key, _, value = part.partition(":")
                    value = value.strip()
                    if key == "Porcje":
                        recipe["servings"] = value
                    elif key == "Posiłek":
                        recipe["meals"] = [meal.strip() for meal in value.split(",") if meal.strip()]
                    elif key == "Dział":
                        recipe["section"] = value
        elif section == "ingredients":
            if line.startswith("- "):
                recipe["ingredients"].append({"text": line[2:].strip(), "label": False})
            elif line.startswith("**") and line.endswith("**"):
                recipe["ingredients"].append({"text": line.strip("*"), "label": True})
        elif section == "method":
            paragraph.append(line)
        elif section == "menu" and line.startswith("- "):
            recipe["menu_slots"].append(line[2:].strip())
    flush_paragraph()
    return recipe


def recipe_photos(session, document_ids: list[int]) -> dict[int, list[dict]]:
    """Dish photos per recipe Document: {id: [{url, thumb_url, caption}]}, presigned MinIO URLs.

    Missing storage configuration or no photos degrade to "no photo", never to an error —
    the recipe text must stay readable.
    """
    if not document_ids:
        return {}
    rows = (
        session.execute(
            select(DocumentImage)
            .where(DocumentImage.document_id.in_(document_ids), DocumentImage.storage_key.is_not(None))
            .order_by(DocumentImage.document_id, DocumentImage.id)
        )
        .scalars()
        .all()
    )
    if not rows:
        return {}
    try:
        from library.config_loader import load_config
        from library.storage import storage_from_config

        storage = storage_from_config(load_config())
        photos: dict[int, list[dict]] = {}
        for row in rows:
            url = storage.presigned_get_url(row.storage_key)
            if url:
                photos.setdefault(row.document_id, []).append(
                    {
                        "url": url,
                        "thumb_url": storage.presigned_get_url(thumb_key(row.storage_key)) or url,
                        "caption": row.caption_text,
                    }
                )
        return photos
    except (SystemExit, Exception):
        logger.exception("Could not build recipe photo URLs")
        return {}


def _recipe_conditions(meal: str | None, wege: bool, query: str | None) -> list:
    conditions = [Document.tags.op("~")(_TAG_RE % re.escape(RECIPE_TAG))]
    if meal:
        conditions.append(Document.tags.op("~")(_TAG_RE % re.escape(meal)))
    if wege:
        conditions.append(Document.tags.op("~")(_TAG_RE % WEGE_TAG))
    if query:
        # Same diacritic folding as DocumentRepository.search_text(): "pęczak" finds "peczak".
        searchable = func.unaccent(
            func.concat_ws(" ", func.coalesce(Document.title, ""), func.coalesce(Document.text_md, ""))
        )
        for token in query.split():
            conditions.append(searchable.ilike(func.unaccent(f"%{token}%")))
    return conditions


@bp.route("/recipes", methods=["GET"])
def get_recipes():
    session = get_scoped_session()
    meal = request.args.get("meal") or None
    if meal and meal not in MEAL_TAGS:
        return jsonify({"status": "error", "message": f"meal must be one of {', '.join(MEAL_TAGS)}"}), 400
    wege = (request.args.get("wege") or "").lower() in ("1", "true", "yes")
    query = (request.args.get("q") or "").strip() or None
    try:
        limit = min(max(int(request.args.get("limit", 50)), 1), 100)
        offset = max(int(request.args.get("offset", 0)), 0)
    except ValueError:
        return jsonify({"status": "error", "message": "limit and offset must be integers"}), 400

    conditions = _recipe_conditions(meal, wege, query)
    total = session.execute(select(func.count()).select_from(Document).where(*conditions)).scalar_one()
    rows = session.execute(
        select(Document.id, Document.title, Document.tags, Document.note, Document.text_md)
        .where(*conditions)
        .order_by(func.lower(Document.title), Document.id)
        .limit(limit)
        .offset(offset)
    ).all()

    # Chip counts ignore the meal/wege/q filters so the buttons keep showing the whole library.
    meal_counts = dict.fromkeys(MEAL_TAGS, 0)
    wege_count = 0
    all_tags = session.execute(select(Document.tags).where(*_recipe_conditions(None, False, None))).scalars().all()
    for raw in all_tags:
        tags = split_tags(raw)
        for tag in tags:
            if tag in meal_counts:
                meal_counts[tag] += 1
        wege_count += WEGE_TAG in tags

    recipes = []
    photos = recipe_photos(session, [row.id for row in rows])
    for row in rows:
        parsed = parse_recipe_markdown(row.text_md)
        first_photo = (photos.get(row.id) or [None])[0]
        recipes.append(
            {
                "id": row.id,
                "thumb_url": first_photo["thumb_url"] if first_photo else None,
                "title": row.title,
                "tags": split_tags(row.tags),
                "servings": parsed["servings"],
                "meals": parsed["meals"],
                "wege": WEGE_TAG in split_tags(row.tags),
                "ingredient_count": len(parsed["ingredients"]),
                "note": row.note,
            }
        )
    return jsonify(
        {
            "status": "success",
            "total": total,
            "recipes": recipes,
            "meals": [{"tag": tag, "label": label, "count": meal_counts[tag]} for tag, label in MEAL_TAGS.items()],
            "wege_count": wege_count,
        }
    )


@bp.route("/recipes/<int:recipe_id>", methods=["GET"])
def get_recipe(recipe_id: int):
    session = get_scoped_session()
    doc = session.execute(
        select(Document).where(Document.id == recipe_id, *_recipe_conditions(None, False, None))
    ).scalar_one_or_none()
    if doc is None:
        return jsonify({"status": "error", "message": "Recipe not found"}), 404
    parsed = parse_recipe_markdown(doc.text_md)
    return jsonify(
        {
            "status": "success",
            "recipe": {
                "id": doc.id,
                "title": doc.title,
                "tags": split_tags(doc.tags),
                "byline": doc.byline,
                "note": doc.note,
                "photos": recipe_photos(session, [doc.id]).get(doc.id, []),
                **parsed,
            },
        }
    )
