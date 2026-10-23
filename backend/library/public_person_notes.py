"""Read the vault notes about public people (`people i firmy/public/...`) into registry fields.

These notes are tiny and free-form: a line of description, a few links (a YouTube channel, a home
page, LinkedIn, a newsletter) and sometimes a ``[[wikilink]]`` to the course the person made. Pure
functions only; ``imports/public_people_import.py`` writes the result to the person registry.
"""

import re
from urllib.parse import urlparse

_WIKILINK = re.compile(r"\[\[([^\]|#]+)(?:#[^\]|]*)?(?:\|[^\]]*)?\]\]")
_URL = re.compile(r"https?://[^\s)>\]]+")
_PREFIX_NOISE = " -:*•\t"
MAX_DESCRIPTION = 300

_HOST_LABELS = (
    (("youtube.com", "youtu.be"), "YouTube"), (("linkedin.com",), "LinkedIn"), (("x.com", "twitter.com"), "X"),
    (("wikipedia.org",), "Wikipedia"), (("github.com",), "GitHub"), (("facebook.com",), "Facebook"),
    (("udemy.com",), "Udemy"), (("lubimyczytac.pl",), "Lubimyczytać"), (("notion.site",), "Notion"),
)
_FOLDER_ROLES = {"podcasterzy": "podcaster", "pisarze": "pisarz"}
_INSTRUCTOR_WORDS = ("kurs", "szkolen", "trener", "wykład", "warsztat")


def label_for_url(url: str) -> str:
    host = (urlparse(url).hostname or url).lower().removeprefix("www.")
    for hosts, label in _HOST_LABELS:
        if any(host == name or host.endswith("." + name) for name in hosts):
            return label
    return host


def parse_person_note(text: str) -> dict:
    """``{"description", "long_description", "links": [{url, label}], "courses": [{title, role}]}``.

    The first line of plain prose is the short description (cut to ``MAX_DESCRIPTION``); all prose becomes
    the long description when there is more than the short one. A URL keeps the words before it as its
    label ("newsletter: https://…"), otherwise the label comes from the host. A ``[[wikilink]]`` is a course
    or training the person made; the words before it decide ``instructor`` ("Autor kursu") or ``author``.
    """
    lines = text.splitlines()
    if lines and lines[0].strip() == "---":
        end = next((i for i, line in enumerate(lines[1:], start=1) if line.strip() == "---"), None)
        if end is not None:
            lines = lines[end + 1:]
    prose: list[str] = []
    links: list[dict] = []
    courses: list[dict] = []
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        titles = [title.strip() for title in _WIKILINK.findall(stripped) if title.strip()]
        urls = [url.rstrip(".,;") for url in _URL.findall(stripped)]
        if titles:
            prefix = _WIKILINK.sub("", stripped)
            prefix = _URL.sub("", prefix).strip(_PREFIX_NOISE).lower()
            role = "instructor" if any(word in prefix for word in _INSTRUCTOR_WORDS) else "author"
            courses.extend({"title": title, "role": role} for title in titles)
        for url in urls:
            label = stripped[:stripped.index(url)].strip(_PREFIX_NOISE) if len(urls) == 1 and not titles else ""
            links.append({"url": url, "label": label[:100] if 0 < len(label) <= 40 else label_for_url(url)})
        if not titles and not urls:
            prose.append(stripped)
    seen: set[str] = set()
    unique_links = []
    for link in links:
        if link["url"] not in seen:
            seen.add(link["url"])
            unique_links.append(link)
    description = prose[0][:MAX_DESCRIPTION] if prose else None
    long_description = "\n\n".join(prose) if len(prose) > 1 or (prose and len(prose[0]) > MAX_DESCRIPTION) else None
    return {"description": description, "long_description": long_description, "links": unique_links, "courses": courses}


def _titled(word: str) -> str:
    return word[:1].upper() + word[1:] if word and word[0].islower() else word


def derive_identity(stem: str) -> dict:
    """A person's name, aliases and a description hint from a note's file name; ``name`` is ``None`` when it is no person.

    "Claudowski - Tomasz Cholewa" is a nickname plus the real name, "Jacek walkiewicz - Mówca motywujący" a name plus
    what they are, a single word ("talkpython") is not a person at all. Surname-first names ("Górczyk Przemek") cannot
    be told apart from the file name: fix those with an override.
    """
    parts = [part.strip() for part in re.split(r"\s+[-–—]\s+", stem.strip()) if part.strip()]
    if not parts:
        return {"name": None, "aliases": [], "hint": None}
    first, rest = parts[0], parts[1:]
    first_tokens, second = first.split(), (rest[0].split() if rest else [])
    if len(first_tokens) == 1 and len(second) >= 2 and all(token[:1].isupper() for token in second):
        return {"name": " ".join(second), "aliases": [first], "hint": None}
    if len(first_tokens) < 2:
        return {"name": None, "aliases": [], "hint": stem}
    return {"name": " ".join(_titled(token) for token in first_tokens), "aliases": [], "hint": " - ".join(rest) or None}


def role_from_folder(relative_folder: str) -> str | None:
    """A role implied by the sub-folder under ``public`` ("podcasterzy" -> "podcaster"); topic folders ("IT") imply none."""
    first = relative_folder.strip("/").split("/")[0] if relative_folder.strip("/") else ""
    return _FOLDER_ROLES.get(first.lower())
