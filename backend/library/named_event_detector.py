"""Text-only detection of named scandals, with optional organization resolution."""

import re

EVENT_INDICATORS = {
    **dict.fromkeys(("afera", "afery", "aferze", "aferę", "aferą"), "afera"),
    **dict.fromkeys(("skandal", "skandalu", "skandalowi", "skandalem", "skandale"), "skandal"),
}
_WORD = re.compile(r"[ \u00a0]([^\W\d_]+(?:-[^\W\d_]+)*)(?![\w-])")
_INDICATOR = re.compile(r"\b(?:" + "|".join(EVENT_INDICATORS) + r")\b", re.IGNORECASE)


def capitalized_word_ends(text: str, start: int, limit: int) -> list[int]:
    """Consume Unicode words separated by exactly one space or NBSP."""
    ends = []
    for _ in range(limit):
        match = _WORD.match(text, start)
        if match is None or not match.group(1)[0].isupper():
            break
        start = match.end()
        ends.append(start)
    return ends


def detect_named_events(text, lookup=None) -> dict[str, dict]:
    events = {}
    for match in _INDICATOR.finditer(text):
        ends = capitalized_word_ends(text, match.end(), 4)
        if not ends:
            continue
        phrase = text[match.end() + 1:ends[-1]]
        if len(ends) == 1 and len(phrase) < 3:
            continue
        organization = lookup(phrase) if lookup is not None and len(ends) >= 2 else None
        name = EVENT_INDICATORS[match.group().casefold()] + " " + (organization[0] if organization else phrase)
        event = events.setdefault(name, {"count": 0, "variants": [], "organization_id": None})
        event["count"] += 1
        if organization:
            event["organization_id"] = organization[1]
        surface = text[match.start():ends[-1]]
        if surface not in event["variants"]:
            event["variants"].append(surface)
    return events
