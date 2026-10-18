"""Parse a cookbook PDF's text into individual recipes.

Pure functions over per-page text (no Flask, no DB, no filesystem), so the same
code can later run from a worker/job. Written for "Insulinooporność. Szybkie
dania" (Makarowska, Musiałowska, ebookpoint) but the recipe shape it detects —
title line, "•" ingredient block, instruction paragraph — is common to many
cookbooks; book-specific values (page ranges, meal-plan context) are passed in
by the CLI wrapper in imports/.

A recipe is delimited structurally, not by font: the first "•" line after a
title starts the ingredient block, the first line that begins a sentence after
it starts the method, and the next title closes the recipe. Titles come in two
shapes: meal-plan style ("obiad: Chilli con carne – 2 porcje") and plain style
(a short capitalised line directly above the ingredients).
"""

import re
from dataclasses import dataclass, field

# ebookpoint stamps every page with the buyer's name/e-mail/licence id; these
# lines must never reach the database or an embedding.
_WATERMARK_RE = re.compile(r"^(ebookpoint kopia dla:.*|[0-9a-f]{32})$")
_MEAL_PREFIX_RE = re.compile(
    r"^(?P<meal>II śniadanie|śniadanie|obiad|kolacja|podwieczorek|przekąska)\s*:\s*(?P<rest>.*)$"
)
_PORTIONS_RE = re.compile(r"^(?P<title>.+?)\s*[–-]\s*(?:ok\.\s*)?(?P<n>\d+(?:[–-]\d+)?)\s*porcj\w*\s*$")
_PORTIONS_ONLY_RE = re.compile(r"^[–-]\s*(?:ok\.\s*)?\d+(?:[–-]\d+)?\s*porcj\w*\s*$")
# "Koktajl piernikowy 300 ml", "Faworki pieczone – ok. 40 ciasteczek": quantity instead of portions.
_UNIT_SUFFIX_RE = re.compile(r"^(?P<title>.+?)\s*[–-]?\s*(?P<n>(?:ok\.\s*)?\d+\s*(?:ml|ciasteczek|ciastek|szt\.?))\s*$")
_BULLET_RE = re.compile(r"^[•▪]\s*")
_NUTRITION_RE = re.compile(r"^\(.*\bkcal\b.*\)$")
_DAY_RE = re.compile(r"^(poniedziałek|wtorek|środa|czwartek|piątek|sobota|niedziela)\b[^.]{0,60}$", re.IGNORECASE)
# Prose boxes that sit after the last recipe of a section (not recipes).
_PROSE_STOP_RE = re.compile(r"^(Przepisy na obiad i kolację|Przepisy na sałatki|Pamiętaj,)")


@dataclass
class Recipe:
    title: str
    meal: str | None = None  # "śniadanie", "obiad", ... when the recipe came from a meal plan
    servings: str | None = None  # "2", "ok. 10" as printed
    nutrition: str | None = None  # printed "(w 1 porcji ok. 500 kcal, B 37 g/T 63 g/W 80 g)" line
    section: str | None = None  # printed category heading, e.g. "Szybkie pasty śniadaniowe"
    notes: list[str] = field(default_factory=list)  # "* ..." tips printed under the title
    ingredients: list[str] = field(default_factory=list)  # bullets; sub-block labels as "**label**"
    method: str = ""
    pages: list[int] = field(default_factory=list)  # 1-based source pages
    # Where a meal plan serves it: [{"month": 1, "week": 2, "day": "poniedziałek – wtorek", "meal": "obiad"}]
    occurrences: list[dict] = field(default_factory=list)

    @property
    def key(self) -> str:
        return normalize_title(self.title)


def normalize_title(title: str) -> str:
    """Case/diacritic-insensitive key; used to dedupe and to match the book's index."""
    from unidecode import unidecode

    text = unidecode(title).lower().replace("\xad", "")
    return re.sub(r"[^a-z0-9]+", " ", text).strip()


def clean_page_text(text: str) -> str:
    """Drop watermarks and soft hyphens; rejoin words hyphenated across lines."""
    text = text.replace("\xad\n", "").replace("\xad", "")
    text = text.replace("ŕ", "à")  # index font renders 'à' as 'ŕ'
    out = []
    for line in text.split("\n"):
        line = line.strip()
        if _WATERMARK_RE.match(line):
            continue
        out.append(line)
    return "\n".join(out)


@dataclass
class _Line:
    text: str
    page: int  # 1-based


def _page_lines(pages: list[str], first: int, last: int) -> list[_Line]:
    """Cleaned, non-empty lines for 1-based pages first..last (inclusive)."""
    lines: list[_Line] = []
    for number in range(first, min(last, len(pages)) + 1):
        for raw in clean_page_text(pages[number - 1]).split("\n"):
            if not raw or raw == str(number):  # blank / the page number itself
                continue
            if lines and _PORTIONS_ONLY_RE.match(raw):
                lines[-1].text = f"{lines[-1].text} {raw}"  # title wrapped before its "– 2 porcje"
                continue
            lines.append(_Line(raw, number))
    return lines


def _is_bullet(text: str) -> bool:
    return bool(_BULLET_RE.match(text))


def _is_continuation(text: str, previous: str) -> bool:
    """A non-bullet line that continues the previous (wrapped) ingredient."""
    first = text[0]
    if first.islower() or first.isdigit() or first in "½⅓¼¾(":
        return True
    if text.startswith(("W WERSJI", "WERSJI")):
        return True
    return previous.rstrip().endswith((",", "(", "/", "lub", "oraz"))


def _is_note(text: str) -> bool:
    return text.startswith("*") or bool(_NUTRITION_RE.match(text))


def _is_weak_title(text: str) -> bool:
    """Plain-style title: a capitalised line that is not a sub-block label or an instruction."""
    if text.startswith(("WEGE", "W WERSJI")) or text.endswith((".", ":", "!", "?")):
        return False
    words = text.split()
    return text[0].isupper() and len(words) <= 10 and not (len(words) > 6 and "," in text)


def _looks_like_heading(text: str) -> bool:
    words = text.split()
    return (
        0 < len(words) <= 6
        and text[0].isupper()
        and not text.endswith((".", "!", "?", ":", ","))
        and not _is_bullet(text)
    )


def _find_title(pending: list[_Line]) -> tuple[int, str, str | None, str | None, list[str], str | None] | None:
    """Locate the title block at the tail of `pending`.

    Returns (start_index, title, meal, servings, nutrition_and_notes, nutrition) or None.
    `pending` holds the non-bullet lines since the previous recipe's ingredient
    block; the title block is its tail, optionally followed by note lines.
    """
    if not pending:
        return None
    # Strong title: meal prefix and/or "– N porcje" suffix.
    for index in range(len(pending) - 1, -1, -1):
        text = pending[index].text
        tail = pending[index + 1 :]
        if not all(_is_note(ln.text) or _is_continuation(ln.text, "") for ln in tail):
            # Something that is not a note sits between this line and the bullets.
            break
        joined = text
        start = index
        portions = _PORTIONS_RE.match(joined)
        prefix = _MEAL_PREFIX_RE.match(joined)
        # A long title wraps: "obiad: Filet w sezamie z …" / "pomidorami – 2 porcje".
        if portions and not prefix and index > 0:
            before = pending[index - 1].text
            if _MEAL_PREFIX_RE.match(before) and not _PORTIONS_RE.match(before):
                joined = f"{before} {text}"
                start = index - 1
                portions = _PORTIONS_RE.match(joined)
                prefix = _MEAL_PREFIX_RE.match(joined)
        elif prefix and not portions and index + 1 < len(pending):
            nxt = pending[index + 1].text
            if _PORTIONS_RE.match(f"{joined} {nxt}"):
                joined = f"{joined} {nxt}"
                tail = pending[index + 2 :]
                portions = _PORTIONS_RE.match(joined)
        if portions or prefix:
            meal = None
            title = joined
            if prefix:
                meal = prefix.group("meal")
                title = _MEAL_PREFIX_RE.match(joined).group("rest")
            servings = None
            match = _PORTIONS_RE.match(title)
            if match:
                title = match.group("title")
                servings = match.group("n")
                if "ok." in joined.split("–")[-1]:
                    servings = f"ok. {servings}"
            else:
                unit = _UNIT_SUFFIX_RE.match(title)
                if unit:
                    title, servings = unit.group("title"), unit.group("n")
            return start, title.strip(), meal, servings, [ln.text for ln in tail], None
        # Not a title — keep walking back only across note-ish lines.
        if not (_is_note(text) or _is_continuation(text, "")):
            break
    # Weak title: a short capitalised line directly above the bullets.
    tail_notes = 0
    for ln in reversed(pending):
        if _is_note(ln.text) or _is_continuation(ln.text, ""):
            tail_notes += 1
        else:
            break
    candidate_index = len(pending) - 1 - tail_notes
    if candidate_index >= 0:
        text = pending[candidate_index].text
        if _is_weak_title(text):
            return candidate_index, text, None, None, [ln.text for ln in pending[candidate_index + 1 :]], None
    return None


def _join_method(lines: list[str]) -> str:
    """Join wrapped lines; a short line ending a sentence closes the paragraph."""
    paragraphs: list[str] = []
    current: list[str] = []
    for text in lines:
        current.append(text)
        if text.endswith((".", "!", "?")) and len(text) < 70:
            paragraphs.append(" ".join(current))
            current = []
    if current:
        paragraphs.append(" ".join(current))
    return "\n\n".join(p.strip() for p in paragraphs if p.strip())


def _is_section_banner(text: str) -> bool:
    """Banners that are not recipe categories: "II MIESIĄC", "I TYDZIEŃ", ALL-CAPS page titles."""
    return text.isupper() or bool(re.search(r"\b(MIESIĄC|TYDZIEŃ)\b", text, re.IGNORECASE))


def _split_tail_headings(method_lines: list[str]) -> tuple[list[str], str | None]:
    """Trailing short heading lines belong to the *next* section, not this method."""
    heading = None
    while method_lines and _looks_like_heading(method_lines[-1]) and not method_lines[-1].startswith("W WERSJI"):
        popped = method_lines.pop()
        if not _is_section_banner(popped):
            heading = popped
    return method_lines, heading


def parse_recipes(
    pages: list[str],
    first_page: int,
    last_page: int,
    *,
    context_for_page=None,
) -> list[Recipe]:
    """Parse every recipe on 1-based pages first_page..last_page (inclusive).

    `context_for_page(page) -> dict` (optional) supplies book-specific context
    (e.g. {"month": 1, "week": 2}) copied into each recipe's `occurrences`.
    The returned list keeps every occurrence; see merge_duplicates().
    """
    lines = _page_lines(pages, first_page, last_page)
    recipes: list[Recipe] = []
    current: Recipe | None = None
    state = "seek"  # seek | ingredients | method
    pending: list[_Line] = []
    section: str | None = None
    day: str | None = None
    last_bullet_text = ""
    method_acc: list[str] = []  # method lines already seen before a later ingredient sub-block

    def finish() -> None:
        nonlocal current, pending, section, method_acc
        if current is None:
            return
        method_lines = [ln.text for ln in pending if not _PROSE_STOP_RE.match(ln.text)]
        # Cut everything from the first prose-box line onward.
        for i, ln in enumerate(pending):
            if _PROSE_STOP_RE.match(ln.text):
                method_lines = [x.text for x in pending[:i]]
                break
        method_lines, trailing = _split_tail_headings(method_lines)
        if trailing:
            section = trailing
        current.method = _join_method(method_acc + method_lines)
        recipes.append(current)
        current = None
        pending = []
        method_acc = []

    for line in lines:
        text = line.text
        if _DAY_RE.match(text) and not _is_bullet(text) and state != "ingredients":
            day = text
            continue
        if _is_bullet(text):
            if state in ("seek", "method"):
                found = _find_title(pending)
                if found:
                    start, title, meal, servings, notes, _ = found
                    carried = pending[:start]
                    pending = carried
                    finish()
                    nutrition = None
                    note_lines = []
                    first_label = None
                    for n in notes:
                        if _NUTRITION_RE.match(n):
                            nutrition = n.strip("()")
                        elif not note_lines and not n.startswith("*") and len(n.split()) <= 3:
                            first_label = n  # "spód" printed above the first ingredient block
                        else:
                            note_lines.append(n)
                    context = context_for_page(line.page) if context_for_page else {}
                    current = Recipe(
                        title=title,
                        meal=meal,
                        servings=servings,
                        nutrition=nutrition,
                        section=section,
                        notes=_merge_notes(note_lines),
                        pages=[line.page],
                        occurrences=[{**context, "day": day, "meal": meal, "page": line.page}],
                    )
                    if first_label:
                        current.ingredients.append(f"**{first_label}**")
                    pending = []
                elif current is not None:
                    # A labelled sub-block of the same recipe ("spód", "krem").
                    label = pending[-1].text if pending and len(pending[-1].text.split()) <= 3 else None
                    carry = pending[:-1] if label else pending
                    method_acc.extend(ln.text for ln in carry)
                    if label:
                        current.ingredients.append(f"**{label}**")
                    pending = []
                else:
                    pending = []
                    continue
            state = "ingredients"
            current.ingredients.append(_BULLET_RE.sub("", text))
            last_bullet_text = text
            if line.page not in current.pages:
                current.pages.append(line.page)
            continue
        if state == "ingredients":
            if _is_continuation(text, last_bullet_text):
                current.ingredients[-1] = f"{current.ingredients[-1]} {text}".strip()
                last_bullet_text = text
                continue
            state = "method"
            pending = [line]
            continue
        pending.append(line)
        if current is not None and line.page not in current.pages and state == "method":
            current.pages.append(line.page)
    finish()
    return recipes


def _merge_notes(note_lines: list[str]) -> list[str]:
    """Join wrapped "* ..." tips into one string each."""
    notes: list[str] = []
    for text in note_lines:
        if text.startswith("*"):
            notes.append(text.lstrip("* ").strip())
        elif notes:
            notes[-1] = f"{notes[-1]} {text}"
    return notes


def merge_duplicates(recipes: list[Recipe]) -> list[Recipe]:
    """Collapse recipes with the same normalised title; keep the fullest text.

    Meal plans repeat dishes across days/weeks; the first/fullest version is the
    document, every serving slot is kept in `occurrences`.
    """
    by_key: dict[str, Recipe] = {}
    for recipe in recipes:
        existing = by_key.get(recipe.key)
        if existing is None:
            by_key[recipe.key] = recipe
            continue
        existing.occurrences.extend(recipe.occurrences)
        for page in recipe.pages:
            if page not in existing.pages:
                existing.pages.append(page)
        if len(recipe.method) + len(" ".join(recipe.ingredients)) > len(existing.method) + len(
            " ".join(existing.ingredients)
        ):
            for attr in ("ingredients", "method", "notes", "nutrition", "servings"):
                setattr(existing, attr, getattr(recipe, attr))
    return list(by_key.values())


def parse_index(pages: list[str], first_page: int, last_page: int) -> dict[str, int]:
    """Parse the book's printed "Indeks przepisów" into {normalised title: page}."""
    entries: dict[str, int] = {}
    buffer = ""
    for line in _page_lines(pages, first_page, last_page):
        text = re.sub(r"^Indeks przepisów\s*", "", line.text, flags=re.IGNORECASE)
        if not text:
            continue
        buffer = f"{buffer} {text}".strip() if buffer else text
        match = re.match(r"^(?P<title>.*?)\s*(?P<page>\d{1,3})$", buffer)
        if match and match.group("title"):
            title = re.sub(r"-\s+-", "-", match.group("title"))
            entries[normalize_title(title)] = int(match.group("page"))
            buffer = ""
        elif re.fullmatch(r"\d{1,3}", buffer):
            buffer = ""
    return entries


def recipe_to_markdown(recipe: Recipe) -> str:
    """Render a recipe as the Document's text_md."""
    parts = [f"# {recipe.title}"]
    meta = []
    if recipe.servings:
        meta.append(f"Porcje: {recipe.servings}")
    if recipe.meal:
        meta.append(f"Posiłek: {recipe.meal}")
    if recipe.section:
        meta.append(f"Dział: {recipe.section}")
    if meta:
        parts.append(" · ".join(meta))
    if recipe.nutrition:
        parts.append(f"_{recipe.nutrition}_")
    for note in recipe.notes:
        parts.append(f"> {note}")
    parts.append("## Składniki")
    for item in recipe.ingredients:
        parts.append(item if item.startswith("**") else f"- {item}")
    if recipe.method:
        parts.append("## Przygotowanie")
        parts.append(recipe.method)
    return "\n\n".join(parts).replace("\n\n- ", "\n- ")
