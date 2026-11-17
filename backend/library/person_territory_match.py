"""Use a document's countries/regions to resolve namesakes and repair mangled names of persons.

The candidates are the people tied to the document's territories (``person_territories``). Three pure
helpers answer, for one mention, whether a candidate is meant:

* ``pick_wikidata_by_territory`` - several Wikidata humans share the name; exactly one of them is a known
  person of the document's territory, so no LLM guess is needed;
* ``find_territory_person`` - the mention (a surname, an inflected form) fits exactly one such person;
* ``find_mangled_territory_person`` - the mention sounds like exactly one such person's name (a
  speech-to-text slip: "Nuzajli" for "al-Nuzaili"); the result is only a proposal for review.

Every helper answers None unless the answer is unique.
"""

from __future__ import annotations

from difflib import SequenceMatcher

from library.ner_channel_glossary import phonetic_key
from library.person_registry import _name_tokens, matches_person_name

MIN_MANGLED_SIMILARITY = 0.84
MIN_MANGLED_LENGTH = 5
MAX_ENDING = 3


def _forms(person: dict) -> list[str]:
    return [person["canonical_name"], *person.get("aliases", [])]


def pick_wikidata_by_territory(candidates: list[dict], territory_people: list[dict]) -> str | None:
    """The QID of the one Wikidata candidate that is a known person of the document's territory."""
    known = {p["wikidata_qid"] for p in territory_people if p.get("wikidata_qid")}
    hits = {c["qid"] for c in candidates if c["qid"] in known}
    return next(iter(hits)) if len(hits) == 1 else None


def find_territory_person(name: str, territory_people: list[dict]) -> dict | None:
    """The ONE territory person the mention names (surname, inflected form, alias)."""
    hits = {}
    for person in territory_people:
        for form in _forms(person):
            if matches_person_name(name, form) or name.casefold() == form.casefold():
                hits[person["id"]] = person
                break
    return next(iter(hits.values())) if len(hits) == 1 else None


def _similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, phonetic_key(a), phonetic_key(b)).ratio()


def _mangled_score(mention_tokens: list[str], form: str) -> float:
    """How well the mention sounds like the tail of ``form`` (hyphens and spaces ignored, a Polish ending
    of up to three letters forgiven); 0 below the threshold."""
    form_tokens = _name_tokens(form)
    count = len(mention_tokens)
    if not form_tokens or count > len(form_tokens):
        return 0.0
    mention = "".join(mention_tokens)
    if len(mention) < MIN_MANGLED_LENGTH:
        return 0.0
    stems = [mention[: len(mention) - cut] for cut in range(0, MAX_ENDING + 1) if len(mention) - cut >= 4]
    best = 0.0
    for size in {count, min(count + 1, len(form_tokens))}:
        tail = "".join(form_tokens[-size:])
        best = max(best, *(_similarity(stem, tail) for stem in stems))
    return best if best >= MIN_MANGLED_SIMILARITY else 0.0


def find_mangled_territory_person(name: str, territory_people: list[dict]) -> dict | None:
    """The ONE territory person whose name the mention sounds like; ties and exact matches never reach here."""
    mention_tokens = _name_tokens(name)
    if not mention_tokens:
        return None
    best: dict[int, tuple[float, dict]] = {}
    for person in territory_people:
        score = max((_mangled_score(mention_tokens, form) for form in _forms(person)), default=0.0)
        if score:
            best[person["id"]] = (score, person)
    if not best:
        return None
    ranked = sorted(best.values(), key=lambda item: -item[0])
    if len(ranked) > 1 and ranked[0][0] - ranked[1][0] < 0.05:
        return None
    return ranked[0][1]
