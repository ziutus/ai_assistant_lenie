"""Per-channel glossary that repairs speech-to-text slips in the text sent to NER.

Auto-captions of one channel keep mangling the same names: doc #10872 (a US-politics channel) has
"Hekset", "Hekseta", "Hexet", "Hexeta" and "He H" for Pete Hegseth. A global fuzzy fixer would be
far too invasive, so entries are bound to a channel (Document.byline) and list the names expected
there. Two mechanisms, both working on a COPY of the text — the stored transcript never changes:

* ``aliases``: exact, case-sensitive phrases replaced by the entry's ``canonical_name``;
* ``fuzzy``: a capitalized word whose phonetic key is close to the last word of ``canonical_name``
  is replaced by that word in the nominative ("Hekseta" -> "Hegseth").

NER then sees one clean name instead of five, and ``restore_original_variants()`` puts the original
spellings back into the entity's surface variants so chip highlighting still finds them in the
transcript. Every replacement is returned (and persisted by entity_service) as an audit trail.
"""

import re
from collections import Counter
from dataclasses import dataclass, field
from difflib import SequenceMatcher

from unidecode import unidecode

MIN_TARGET_LENGTH = 5
MIN_SIMILARITY = 0.84

_WORD_RE = re.compile(r"[^\W\d_]+")
_DEVOICE = str.maketrans("gbdzwv", "kptsff")


@dataclass(frozen=True)
class GlossaryEntry:
    id: int | None
    canonical_name: str
    aliases: tuple[str, ...] = ()
    fuzzy: bool = True


@dataclass
class GlossaryResult:
    text: str
    # (entry id, original surface, replacement) -> occurrences
    replacements: Counter = field(default_factory=Counter)


def phonetic_key(word: str) -> str:
    """Coarse sound-alike key: ASCII, lowercase, x->ks, th->t, devoiced consonants, no doubles."""
    key = unidecode(word).lower().replace("x", "ks").replace("th", "t").replace("ph", "f")
    key = key.translate(_DEVOICE)
    return re.sub(r"(.)\1+", r"\1", key)


def _target_word(entry: GlossaryEntry) -> str | None:
    words = _WORD_RE.findall(entry.canonical_name)
    target = words[-1] if words else ""
    return target if len(target) >= MIN_TARGET_LENGTH else None


def _sounds_like(word: str, target_key: str) -> bool:
    return SequenceMatcher(None, phonetic_key(word), target_key).ratio() >= MIN_SIMILARITY


def apply_glossary(text: str, entries: list[GlossaryEntry]) -> GlossaryResult:
    """Return the text with the entries' aliases and sound-alike words replaced, plus the audit."""
    result = GlossaryResult(text=text)
    if not text or not entries:
        return result

    for entry in entries:
        for alias in sorted((a.strip() for a in entry.aliases if a and a.strip()), key=len, reverse=True):
            pattern = re.compile(r"(?<![^\W_])" + re.escape(alias) + r"(?![^\W_])")
            result.text = pattern.sub(
                lambda match, entry=entry: _record(result, entry, match.group(), entry.canonical_name),
                result.text,
            )

    fuzzy_targets = [
        (entry, target, phonetic_key(target))
        for entry in entries if entry.fuzzy and (target := _target_word(entry))
    ]
    if fuzzy_targets:
        known_targets = {target.casefold() for _, target, _ in fuzzy_targets}

        def replace_word(match: re.Match) -> str:
            word = match.group()
            if not word[0].isupper() or word.casefold() in known_targets:
                return word
            for entry, target, key in fuzzy_targets:
                if _sounds_like(word, key):
                    return _record(result, entry, word, target)
            return word

        result.text = _WORD_RE.sub(replace_word, result.text)
    return result


def _record(result: GlossaryResult, entry: GlossaryEntry, original: str, replacement: str) -> str:
    result.replacements[(entry.id, original, replacement)] += 1
    return replacement


def restore_original_variants(groups: dict[tuple[str, str], dict], replacements: Counter) -> None:
    """Add the original spellings to the surface variants of groups built from replaced text.

    Variants are what chapter filtering and chip highlighting search for in the stored transcript,
    which still contains the original (mis-heard) forms.
    """
    originals: dict[str, set[str]] = {}
    for (_entry_id, original, replacement) in replacements:
        originals.setdefault(replacement, set()).add(original)
    if not originals:
        return
    for group in groups.values():
        variants = list(group.get("variants", []))
        for variant in list(variants):
            for replacement, sources in originals.items():
                if re.search(r"(?<![^\W_])" + re.escape(replacement) + r"(?![^\W_])", variant):
                    for source in sorted(sources):
                        restored = variant.replace(replacement, source)
                        if restored not in variants:
                            variants.append(restored)
        group["variants"] = variants
