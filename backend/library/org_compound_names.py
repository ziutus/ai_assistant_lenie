"""Merge NER-grounded organization names split around Polish responsibility phrases."""

import re
from collections import Counter


def _surface_key(value: str) -> str:
    return " ".join(value.split()).casefold()


def merge_compound_org_names(text: str, groups: dict) -> list[tuple]:
    """Merge HEAD ds./do spraw TAIL (ACRONYM), preserving standalone mentions.

    All three components must resolve unambiguously to existing orgName groups.
    Counts reflect complete pattern occurrences; raw lemmas are a stable union.
    Existing canonical groups are left untouched, making repeated calls inert.
    """
    aliases: dict[str, set[tuple]] = {}
    for key, group in groups.items():
        if key[0] != "orgName":
            continue
        for value in [key[1], *group.get("variants", [])]:
            normalized = _surface_key(value)
            if normalized:
                aliases.setdefault(normalized, set()).add(key)
    if not aliases:
        return []

    # Longest alternatives first avoid consuming only a suffix of a known name.
    alternatives = "|".join(
        r"\s+".join(re.escape(token) for token in value.split())
        for value in sorted(aliases, key=lambda value: (-len(value), value))
    )
    pattern = re.compile(
        rf"(?<!\w)(?P<head>(?i:{alternatives}))(?!\w)\s+"
        rf"(?i:ds\.|do\s+spraw)\s+(?P<tail>(?i:{alternatives}))(?!\w)"
        r"\s+\(\s*(?P<acronym>[A-Z0-9]{2,8})\s*\)",
    )
    existing_names = {_surface_key(key[1]) for key in groups if key[0] == "orgName"}
    pending: dict[tuple, dict] = {}
    consumed: Counter = Counter()
    canonical_keys: dict[str, tuple] = {}
    for match in pattern.finditer(text):
        head, tail, acronym = (" ".join(match[name].split()) for name in ("head", "tail", "acronym"))
        component_sets = [aliases.get(_surface_key(value), set()) for value in (head, tail, acronym)]
        if any(len(keys) != 1 for keys in component_sets):
            continue
        components = [next(iter(keys)) for keys in component_sets]
        if len(set(components)) != 3 or _surface_key(head) == _surface_key(tail):
            continue
        canonical = f"{head} ds. {tail} ({acronym})"
        canonical_normalized = _surface_key(canonical)
        if canonical_normalized in existing_names:
            continue
        key = canonical_keys.setdefault(canonical_normalized, ("orgName", canonical))
        group = pending.setdefault(key, {"count": 0, "variants": [], "raw_lemmas": []})
        group["count"] += 1
        full_phrase = " ".join(match.group().split())
        phrase = " ".join(text[match.start():match.end("tail")].split())
        for variant in [full_phrase, f"{phrase} {acronym}", phrase, acronym]:
            if variant not in group["variants"]:
                group["variants"].append(variant)
        for component in components:
            consumed[component] += 1
            for lemma in groups[component].get("raw_lemmas", []):
                if lemma not in group["raw_lemmas"]:
                    group["raw_lemmas"].append(lemma)

    for key, count in consumed.items():
        groups[key]["count"] -= count
        if groups[key]["count"] <= 0:
            del groups[key]
    groups.update(pending)
    return list(pending)
