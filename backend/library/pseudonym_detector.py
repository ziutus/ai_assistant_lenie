"""Text-only detection of explicitly quoted person pseudonyms."""

import re

PSEUDONYM_CUES = (
    "ps.", "pseud.", "pseudonim", "pseudonimem", "pseudonimu",
    "znany jako", "znana jako", "znani jako", "znanego jako", "znanej jako", "znanym jako", "znaną jako",
    "zwany", "zwana", "zwanym", "zwanej",
    "vel", "alias", "a.k.a.", "aka",
)

_WORD = r"[^\W\d_]+(?:-[^\W\d_]+)*"
_CUES = "|".join(re.escape(cue) for cue in sorted(PSEUDONYM_CUES, key=len, reverse=True))
# Lookahead permits checking each word start, even if a preceding lowercase word
# belongs to an earlier candidate. Capitalization is checked with Unicode isupper().
_PATTERN = re.compile(
    rf"(?<![\w-])(?=(?P<surface>(?P<person>{_WORD}(?:[ \u00a0]+{_WORD}){{1,3}})"
    rf"[ ,\u00a0(]+(?i:{_CUES})[ \u00a0]*:?[ \u00a0]*"
    r'''(?:"(?P<double>[^"\r\n]+)"|[„“](?P<curly>[^”\r\n]+)”|'''
    r"«(?P<angle>[^»\r\n]+)»|'(?P<single>[^'\r\n]+)')))"
)


def detect_pseudonyms(text: str) -> list[dict]:
    """Return unique person/pseudonym pairs in text order, preserving surfaces."""
    result = []
    seen = set()
    accepted_end = 0
    for match in _PATTERN.finditer(text):
        if match.start() < accepted_end:
            continue
        person = match["person"]
        if not all(word[0].isupper() for word in person.split()):
            continue
        pseudonym = next(match[key] for key in ("double", "curly", "angle", "single") if match[key]).strip()
        if not 2 <= len(pseudonym) <= 40 or not 1 <= len(pseudonym.split()) <= 4:
            continue
        if pseudonym.casefold() in {word.casefold() for word in person.split()}:
            continue
        accepted_end = match.end("surface")
        key = (person.casefold(), pseudonym.casefold())
        if key not in seen:
            seen.add(key)
            result.append({"person": person, "pseudonym": pseudonym, "surface": match["surface"]})
    return result
