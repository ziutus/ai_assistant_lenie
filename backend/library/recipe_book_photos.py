"""Find the dish photos of a cookbook PDF and match them to recipes.

Cookbook photos carry no captions, so the match is decided by (1) layout — a
photo sitting on a page with exactly one recipe belongs to it — and (2) for
the rest, a vision model that sees the photo plus the titles of the recipes
printed nearby and answers with an index or "none".

PyMuPDF (fitz) is imported lazily so importing this module stays cheap; the
ebookpoint licence stamp is page *text*, so it is redacted from the in-memory
page before rendering and never reaches the saved JPEG.
"""

import base64
import json
import re
from dataclasses import dataclass, field

from library.recipe_book_parser import Recipe

_WATERMARK_RE = re.compile(r"ebookpoint kopia dla:|^[0-9a-f]{32}$")
# A dish photo is an image without an alpha mask that covers (nearly) the whole
# page. Text pages only carry decoration (title banners, leaf cut-outs: small
# and masked), which must never be mistaken for a photo.
FULL_PAGE_SHARE = 0.85
MAX_PHOTO_PAGE_TEXT = 40  # characters of real text a photo page may still carry
_WATERMARK_LINE_RE = re.compile(r"ebookpoint kopia dla:[^\n]*|[0-9a-f]{32}")


@dataclass
class Photo:
    """A full-page dish photo (see find_photos())."""

    page: int  # 1-based
    rect: tuple[float, float, float, float]
    full_page: bool
    index: int = 0  # position among the book's photos, reading order


@dataclass
class PhotoMatch:
    photo: Photo
    recipe_key: str | None
    method: str  # "sole" | "vision" | "none"
    confidence: float
    candidates: list[str] = field(default_factory=list)
    dish: str | None = None


def _visible_text_length(page) -> int:
    text = _WATERMARK_LINE_RE.sub("", page.get_text())
    return len("".join(text.split())) - len(str(page.number + 1))  # minus the printed page number


def find_photos(doc) -> list[Photo]:
    """Full-page dish photos of an open fitz document, one per page, in reading order."""
    import fitz

    photos: list[Photo] = []
    for number, page in enumerate(doc, 1):
        page_area = page.rect.width * page.rect.height
        for info in page.get_image_info():
            rect = fitz.Rect(info["bbox"]) & page.rect
            if info.get("has-mask") or rect.is_empty or rect.width * rect.height / page_area < FULL_PAGE_SHARE:
                continue
            photos.append(
                Photo(page=number, rect=(page.rect.x0, page.rect.y0, page.rect.x1, page.rect.y1), full_page=True)
            )
            break
    for index, photo in enumerate(photos):
        photo.index = index
    return photos


def render_photo(doc, photo: Photo, *, dpi: int = 150, quality: int = 85) -> bytes:
    """JPEG of the photo region with the licence stamp and any overlaid text removed."""
    import fitz

    page = doc[photo.page - 1]
    clip = fitz.Rect(*photo.rect)
    for block in page.get_text("dict")["blocks"]:
        for line in block.get("lines", []):
            text = "".join(span["text"] for span in line["spans"]).strip()
            bbox = fitz.Rect(line["bbox"])
            if _WATERMARK_RE.search(text) or bbox.intersects(clip):
                page.add_redact_annot(bbox, fill=False)
    page.apply_redactions(images=fitz.PDF_REDACT_IMAGE_NONE)
    pixmap = page.get_pixmap(clip=clip, dpi=dpi, colorspace=fitz.csRGB)
    return pixmap.tobytes("jpeg", jpg_quality=quality)


def recipes_by_page(occurrences: list[Recipe]) -> dict[int, list[Recipe]]:
    """Every parsed occurrence (not the merged ones) indexed by each page it spans."""
    index: dict[int, list[Recipe]] = {}
    for recipe in occurrences:
        for page in range(min(recipe.pages), max(recipe.pages) + 1):
            index.setdefault(page, []).append(recipe)
    return index


def candidates_for(photo: Photo, index: dict[int, list[Recipe]], *, reach: int = 2) -> list[Recipe]:
    """Recipes a photo can depict: the same page for inline photos, ±reach pages for full-page ones."""
    pages = range(photo.page - reach, photo.page + reach + 1) if photo.full_page else [photo.page]
    seen: dict[str, Recipe] = {}
    for page in pages:
        for recipe in index.get(page, []):
            seen.setdefault(recipe.key, recipe)
    return list(seen.values())


VISION_MODEL = "google/gemma-4-31B-it"


def vision_prompt(titles: list[str]) -> str:
    listing = "\n".join(f"{i}: {title}" for i, title in enumerate(titles))
    return (
        "To zdjęcie pochodzi z książki kucharskiej. Poniżej tytuły przepisów wydrukowanych w pobliżu zdjęcia.\n"
        "Napisz krótko po polsku, co jest na zdjęciu (pole dish), i wskaż numer przepisu, który zdjęcie przedstawia "
        "(pole index). Jeśli żaden nie pasuje albo nie ma pewności, ustaw index na null. "
        "W polu confidence podaj pewność od 0 do 1. Odpowiedz wyłącznie obiektem JSON: "
        '{"dish": "...", "index": 0, "confidence": 0.9}.\n\n'
        f"Przepisy:\n{listing}"
    )


def match_with_vision(jpeg: bytes, titles: list[str], *, model: str = VISION_MODEL) -> tuple[int | None, float, str]:
    """Ask the vision model which of `titles` the photo shows: (index or None, confidence, dish)."""
    from library.ai import ai_ask

    raw = ""
    for _attempt in range(3):  # the gateway occasionally answers with nothing (2 of 157 photos)
        response = ai_ask(
            vision_prompt(titles),
            model,
            temperature=0,
            max_token_count=1000,  # the model spends ~350 tokens thinking before the JSON
            operation="recipe_photo_match",
            image_base64=base64.b64encode(jpeg).decode("ascii"),
            image_media_type="image/jpeg",
        )
        raw = response.response_text or ""
        if "{" in raw and "}" in raw:
            break
    try:
        # The gateway rejects json_schema together with an image, so the JSON
        # arrives as free text, usually inside a ```json fence.
        data = json.loads(raw[raw.index("{") : raw.rindex("}") + 1])
        index = data.get("index")
        if not isinstance(index, int) or not 0 <= index < len(titles):
            index = None
        return index, float(data.get("confidence") or 0), str(data.get("dish") or "")
    except (ValueError, TypeError, AttributeError):
        return None, 0.0, ""


def match_photo(
    photo: Photo,
    jpeg_for_vision: bytes,
    index: dict[int, list[Recipe]],
    *,
    min_confidence: float = 0.6,
    vision=match_with_vision,
) -> PhotoMatch:
    candidates = candidates_for(photo, index)
    keys = [recipe.key for recipe in candidates]
    if not candidates:
        return PhotoMatch(photo, None, "none", 0.0)
    if len(candidates) == 1 and not photo.full_page:
        return PhotoMatch(photo, keys[0], "sole", 1.0, keys)
    chosen, confidence, dish = vision(jpeg_for_vision, [recipe.title for recipe in candidates])
    if chosen is None or confidence < min_confidence:
        return PhotoMatch(photo, None, "vision", confidence, keys, dish)
    return PhotoMatch(photo, keys[chosen], "vision", confidence, keys, dish)


def thumb_key(storage_key: str) -> str:
    """documents/<id>/images/0.jpg -> documents/<id>/images/0_thumb.jpg (derived, not stored in the DB)."""
    return storage_key.removesuffix(".jpg") + "_thumb.jpg"
