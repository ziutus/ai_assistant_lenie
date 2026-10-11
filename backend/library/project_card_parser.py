"""Parse printed project-card PDFs ("Robotyka – 100 projektów") into card records.

One PDF page is one card with a fixed layout: a letter-spaced header (series,
group), topic, title, tagline, description, then labelled sections (WIEK, CZAS,
POZIOM TRUDNOŚCI, MECHANIZM, JAK TO DZIAŁA, MATERIAŁY, NARZĘDZIA, KROKI, JEŚLI
NIE DZIAŁA, BEZPIECZEŃSTWO, WARIANTY). The layout is recognised from the text
layer plus font sizes (title ≥ 40 pt, tagline ~21 pt) — no OCR.

``parse_lines()`` is pure (a list of ``(text, font_size)``) so it is testable
without a PDF; ``parse_card_pdf()`` reads the first page with PyMuPDF. The
records match ``library.project_cards.normalize_import_card()``; the parser
only extracts, ``flag_card()`` adds heuristic review flags (a step uses an
item that is not listed, a hazardous tool without an adult, ...).

Known layout quirks handled here: the tools list is rendered *after* the
troubleshooting block, section headers have their letters spaced out
("W I E K"), and words are hyphen-split across lines.
"""

from __future__ import annotations

import csv
import pathlib
import re

HEADERS = {
    "WIEK": "age", "CZAS": "time", "POZIOMTRUDNOŚCI": "difficulty", "MECHANIZM": "mechanism",
    "JAKTODZIAŁA": "how", "MATERIAŁY": "materials", "NARZĘDZIA": "tools", "KROKI": "steps",
    "JEŚLINIEDZIAŁA": "troubleshooting", "BEZPIECZEŃSTWO": "safety", "WARIANTY": "variants",
}
_SPACED = re.compile(r"^(?:\S ){3,}\S$")
_QTY = re.compile(r"^\d+(?:[.,]\d+)?(?: ?(?:cm|m|g|kg|ml|szt\.?))?$")
_FOOTER = re.compile(r"^\d{3} · ")
_QUOTES = {"“", "”", '"', "„"}
_DIFFICULTY = {"łatwy": 1, "średni": 2, "trudny": 3}
# word breaks the PDF itself bakes into table cells; extend when a new card shows one
_BROKEN_WORDS = {"szaszłykó w": "szaszłyków"}
_HYPHENS = ("‐", "­")
_TITLE_MIN_SIZE = 40
_TAGLINE_SIZE = (19, 25)
_TOPIC_MAX_SIZE = 15

# (regex in steps, regex in materials/tools, label): an item used in a step must be listed
_STEM_CHECK = [
    (r"nakr[ęe]tk", r"nakr[ęe]tk", "nakrętka"), (r"silnik", r"silnik", "silnik"),
    (r"bateri", r"bateri", "baterie"),
    (r"pistolet|klej(?:u|em)? na gor", r"pistolet|klej na gor", "pistolet do kleju"),
    (r"ta[śs]m", r"ta[śs]m", "taśma"), (r"no[żz]yczk", r"no[żz]yczk", "nożyczki"),
    (r"ni[ćc]|nici|nici[ąa]", r"ni[ćc]|nici|sznur|[żz]y[łl]k", "nić"), (r"sznurk", r"sznur", "sznurek"),
    (r"patycz", r"patycz|ołówek|szasz", "patyczek"), (r"balon", r"balon", "balon"),
    (r"gumk", r"gumk|recept", "gumka"), (r"s[łl]omk", r"s[łl]omk", "słomka"),
    (r"kubecz", r"kubecz|pojemnik", "kubeczek"), (r"butelk", r"butelk", "butelka"),
    (r"drut", r"drut", "drut"), (r"led|diod", r"led|diod", "dioda"),
    (r"magnes", r"magnes", "magnes"), (r"[śs]rub", r"[śs]rub", "śruba"),
    (r"strzykaw", r"strzykaw", "strzykawka"), (r"linijk", r"linijk", "linijka"),
    (r"marker|mazak|kredk|farb", r"marker|mazak|kredk|farb", "pisaki/farby"),
    (r"no[żz]em|nożyk|n[óo][żz] do", r"n[óo][żz]", "nóż"),
]
_HAZARD = ["nóż do tapet", "nożyk", "gorąco", "lutow", "pistolet", "piła", "wiertark", "ostr"]


def _join(parts: list[str]) -> str:
    out = ""
    for part in parts:
        part = part.strip()
        if not part:
            continue
        if out.endswith(_HYPHENS) or (out.endswith("-") and part[:1].islower()):
            out = out[:-1] + part
        else:
            out = f"{out} {part}" if out else part
    out = re.sub(r"(\d)- (\d)", r"\g<1>-\g<2>", out.strip())
    for broken, fixed in _BROKEN_WORDS.items():
        out = out.replace(broken, fixed)
    return out


def _is_symbol(text: str) -> bool:
    return len(text) == 1 and not text.isalnum()


def read_lines(page) -> list[tuple[str, float]]:
    """Text lines of a PyMuPDF page as ``(text, largest font size)`` in reading order."""
    lines = []
    for block in page.get_text("dict")["blocks"]:
        for line in block.get("lines", []):
            text = "".join(span["text"] for span in line["spans"]).strip()
            sizes = [span["size"] for span in line["spans"] if span["text"].strip()]
            if text:
                lines.append((text, max(sizes) if sizes else 0))
    return lines


def _parse_materials(lines: list[str]) -> list[dict]:
    items: list[dict] = []
    for text in lines:
        if _QTY.match(text):
            items.append({"qty": text, "name": []})
        elif items:
            items[-1]["name"].append(text)
    return [{"qty": item["qty"], "name": _join(item["name"])} for item in items]


def _parse_steps(lines: list[str]) -> list[str]:
    steps: list[list[str]] = []
    for text in lines:
        if re.fullmatch(r"\d{2}", text):
            steps.append([])
        elif steps:
            steps[-1].append(text)
    return [_join(step) for step in steps]


def _parse_troubleshooting(lines: list[str]) -> list[dict]:
    items: list[dict] = []
    for text in lines:
        if text.startswith("⚠"):
            items.append({"problem": text.lstrip("⚠ ").strip(), "solution": []})
        elif items:
            items[-1]["solution"].append(text)
    return [{"problem": item["problem"], "solution": _join(item["solution"])} for item in items]


def _split_on(lines: list[str], separator: str) -> list[str]:
    items: list[str] = []
    current: list[str] = []
    for text in lines:
        if text == separator:
            if current:
                items.append(_join(current))
            current = []
        else:
            current.append(text)
    if current:
        items.append(_join(current))
    return [item for item in items if item]


def _split_sections(lines: list[tuple[str, float]]):
    top: list[tuple[str, float]] = []
    sections: dict[str, list[str]] = {}
    spaced_other: list[str] = []
    current = None
    for text, size in lines:
        if _SPACED.match(text):
            collapsed = "".join(text.split())
            key = HEADERS.get(collapsed)
            if key:
                current = key
                sections[current] = []
            else:
                spaced_other.append(collapsed)
                if current is not None:
                    current = "bottom"
                    sections.setdefault("bottom", [])
            continue
        if current is None:
            top.append((text, size))
        else:
            sections.setdefault(current, []).append(text)
    return top, sections, spaced_other


def _first_value(section: list[str]) -> str:
    return next((text for text in section if not _is_symbol(text)), "")


def parse_lines(lines: list[tuple[str, float]], *, number: str, filename: str = "",
                page_pt: tuple[int, int] | None = None, images: int = 0) -> dict:
    """Build a card record from ``(text, font_size)`` lines of one card page."""
    card: dict = {"number": number, "file": filename, "flags": []}
    top, sections, spaced_other = _split_sections(lines)
    card["series_raw"] = spaced_other[0] if spaced_other else ""
    card["group_raw"] = spaced_other[1] if len(spaced_other) > 1 else ""

    topic, title, tagline, description = [], [], [], []
    for text, size in top:
        if _is_symbol(text):
            continue
        if size >= _TITLE_MIN_SIZE:
            title.append(text)
        elif _TAGLINE_SIZE[0] <= size < _TAGLINE_SIZE[1] and title:
            tagline.append(text)
        elif size < _TOPIC_MAX_SIZE and not title:
            topic.append(text)
        elif title and tagline:
            description.append(text)
    card.update(topic=_join(topic), title=_join(title), tagline=_join(tagline), description=_join(description))

    age, time_text, difficulty = (_first_value(sections.get(key, [])) for key in ("age", "time", "difficulty"))
    mechanism = _join([text for text in sections.get("mechanism", []) if not _is_symbol(text)])
    card.update(age_raw=age, time_raw=time_text, difficulty_raw=difficulty, mechanism=mechanism)
    age_range = re.match(r"^(\d+)\s*[-–]\s*(\d+)(?:\s*lat)?$", age)
    age_open = re.match(r"^(\d+)\+$", age)
    card["age_min"] = int(age_range.group(1)) if age_range else int(age_open.group(1)) if age_open else None
    card["age_max"] = int(age_range.group(2)) if age_range else None
    duration = re.match(r"^(\d+)(?:\s*[-–]\s*(\d+))?\s*(min|godz)", time_text)
    if duration:
        factor = 60 if duration.group(3) == "godz" else 1
        card["time_min"] = int(duration.group(1)) * factor
        card["time_max"] = int(duration.group(2)) * factor if duration.group(2) else card["time_min"]
    else:
        card["time_min"] = card["time_max"] = None
    card["difficulty"] = _DIFFICULTY.get(difficulty.lower())

    card["how_it_works"] = _join(sections.get("how", []))
    card["materials"] = _parse_materials(sections.get("materials", []))
    card["steps"] = _parse_steps(sections.get("steps", []))

    # the troubleshooting block is followed by the footer and the displaced tools list
    troubleshooting = sections.get("troubleshooting", [])
    footer_at = next((i for i, text in enumerate(troubleshooting) if _FOOTER.match(text)), None)
    stray_tools: list[str] = []
    card["series_footer"] = ""
    if footer_at is not None:
        card["series_footer"] = troubleshooting[footer_at].split("·", 1)[1].strip()
        stray_tools = troubleshooting[footer_at + 1:]
        troubleshooting = troubleshooting[:footer_at]
    card["troubleshooting"] = _parse_troubleshooting(troubleshooting)
    card["tools"] = _split_on([t for t in sections.get("tools", []) + stray_tools if t not in _QUOTES], "✚")
    card["safety"] = _join([t for t in sections.get("safety", []) if t not in _QUOTES]).rstrip("“” ")
    card["variants"] = _split_on([t for t in sections.get("variants", []) if t not in _QUOTES], "✦")

    card["page_pt"] = list(page_pt) if page_pt else []
    card["images"] = images
    card["needs_adult"] = "dorosł" in (card["safety"] + " ".join(card["tools"])).lower()
    flag_card(card)
    return card


def flag_card(card: dict) -> None:
    """Append heuristic review flags to ``card["flags"]`` (never changes the content)."""
    flags = card["flags"]
    for key in ("title", "tagline", "description", "how_it_works", "safety",
                "materials", "steps", "tools", "variants", "troubleshooting"):
        if not card[key]:
            flags.append(f"missing:{key}")
    for key, flag in (("age_min", "age_unparsed"), ("time_min", "time_unparsed"), ("difficulty", "difficulty_unparsed")):
        if card[key] is None:
            flags.append(flag)
    if len(card["steps"]) < 3:
        flags.append("few_steps")

    inventory = " ".join([m["name"] for m in card["materials"]] + card["tools"]).lower()
    steps_text = " ".join(card["steps"]).lower()
    for in_steps, in_inventory, label in _STEM_CHECK:
        if re.search(in_steps, steps_text) and not re.search(in_inventory, inventory):
            flags.append(f"step_uses_unlisted:{label}")
    hazard_text = f"{inventory} {card['safety']}".lower()
    for hazard in _HAZARD:
        if hazard in hazard_text and not card["needs_adult"]:
            flags.append(f"hazard_no_adult:{hazard}")
            break
    if "dorosł" in inventory and "dorosł" not in card["safety"].lower():
        flags.append("adult_tool_but_safety_silent")
    if card["needs_adult"] and card["age_min"] is not None and card["age_min"] <= 4:
        flags.append("adult_needed_young_age")
    if card["difficulty"] == 1 and card["time_min"] and card["time_min"] > 60:
        flags.append("easy_but_long")
    if any(not material["name"] for material in card["materials"]):
        flags.append("material_without_name")
    if "?" in card["title"] + card["description"]:
        flags.append("stray_question_mark")


def parse_card_pdf(path: str | pathlib.Path) -> dict:
    """Parse the first page of a card PDF named ``NNN - Title.pdf``."""
    import fitz  # PyMuPDF; imported lazily so the pure parser works without it

    path = pathlib.Path(path)
    with fitz.open(path) as document:
        page = document[0]
        return parse_lines(
            read_lines(page), number=path.stem[:3], filename=path.name,
            page_pt=(round(page.rect.width), round(page.rect.height)), images=len(page.get_images()),
        )


def parse_card_dir(directory: str | pathlib.Path) -> list[dict]:
    """Parse every ``*.pdf`` in a directory; a failing file becomes a ``PARSE_ERROR`` record."""
    cards = []
    for path in sorted(pathlib.Path(directory).glob("*.pdf")):
        try:
            cards.append(parse_card_pdf(path))
        except Exception as exc:  # keep going: one bad PDF must not hide the other 99
            cards.append({"number": path.stem[:3], "file": path.name, "flags": [f"PARSE_ERROR:{exc}"]})
    return cards


REVIEW_COLUMNS = ["nr", "tytuł", "grupa", "temat", "wiek", "czas", "poziom", "mechanizm", "kroki", "materiały",
                  "dorosły", "flagi"]


def write_review_csv(cards: list[dict], path: str | pathlib.Path) -> None:
    """Spreadsheet-friendly summary (``;``-separated, BOM for Excel) with one row per card."""
    with open(path, "w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle, delimiter=";")
        writer.writerow(REVIEW_COLUMNS)
        for card in cards:
            writer.writerow([
                card["number"], card.get("title"), card.get("group_raw"), card.get("topic"), card.get("age_raw"),
                card.get("time_raw"), card.get("difficulty_raw"), card.get("mechanism"),
                len(card.get("steps", [])), len(card.get("materials", [])), card.get("needs_adult"),
                " | ".join(card["flags"]),
            ])
