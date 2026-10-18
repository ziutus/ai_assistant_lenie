"""Unit tests for library.ner_channel_glossary — per-channel repair of speech-to-text name slips."""

import pytest

pytest.importorskip("unidecode")

from library.ner_channel_glossary import (  # noqa: E402
    GlossaryEntry,
    apply_glossary,
    phonetic_key,
    restore_original_variants,
)

HEGSETH = GlossaryEntry(1, "Pete Hegseth", aliases=("He H",))
RUBIO = GlossaryEntry(2, "Marco Rubio")


class TestPhoneticKey:
    @pytest.mark.parametrize("word", ["Hegseth", "Hekset", "Hexet", "Hexeta"[:-1], "Hegset"])
    def test_sound_alikes_share_a_key(self, word):
        assert phonetic_key(word) == phonetic_key("Hegseth")


class TestApplyGlossary:
    @pytest.mark.parametrize("variant", ["Hekset", "Hekseta", "Hexet", "Hexeta", "Hegsetem"])
    def test_doc_10872_variants_become_the_surname(self, variant):
        result = apply_glossary(f"Wczoraj {variant} powiedział, że Pentagon odpowie.", [HEGSETH])
        assert result.text == "Wczoraj Hegseth powiedział, że Pentagon odpowie."
        assert dict(result.replacements) == {(1, variant, "Hegseth"): 1}

    def test_first_name_is_kept(self):
        assert apply_glossary("Pete Hekset i Pete Hegseth", [HEGSETH]).text == "Pete Hegseth i Pete Hegseth"

    def test_alias_phrase_becomes_the_canonical_name(self):
        result = apply_glossary("Szef Pentagonu He H odpowiada.", [HEGSETH])
        assert result.text == "Szef Pentagonu Pete Hegseth odpowiada."

    def test_alias_is_case_sensitive_and_needs_word_boundaries(self):
        text = "the He Hmm and he h and Ahe H"
        assert apply_glossary(text, [HEGSETH]).text == text

    def test_lowercase_words_are_never_replaced(self):
        text = "hexet i hekset"
        assert apply_glossary(text, [HEGSETH]).text == text

    def test_unrelated_capitalized_words_are_left_alone(self):
        text = "Hegel, Heisenberg, Helsinki, Hessen, Heksa i Rubin"
        assert apply_glossary(text, [HEGSETH, RUBIO]).text == text

    def test_several_entries_and_counts(self):
        result = apply_glossary("Rubi powiedział to samo co Hexet. Hexet się zgodził.", [HEGSETH, RUBIO])
        assert result.text == "Rubio powiedział to samo co Hegseth. Hegseth się zgodził."
        assert result.replacements[(1, "Hexet", "Hegseth")] == 2
        assert result.replacements[(2, "Rubi", "Rubio")] == 1

    def test_fuzzy_off_keeps_only_aliases(self):
        entry = GlossaryEntry(3, "Pete Hegseth", aliases=("He H",), fuzzy=False)
        assert apply_glossary("Hexet i He H", [entry]).text == "Hexet i Pete Hegseth"

    def test_short_surnames_are_not_fuzzy_matched(self):
        entry = GlossaryEntry(4, "Joe Biden")
        text = "Bider i Biden"
        assert apply_glossary(text, [entry]).text == text

    def test_empty_inputs(self):
        assert apply_glossary("", [HEGSETH]).text == ""
        assert apply_glossary("Hexet", []).text == "Hexet"


class TestRestoreOriginalVariants:
    def test_original_spellings_are_added_to_variants(self):
        result = apply_glossary("Hexeta i Hekset oraz He H", [HEGSETH])
        groups = {
            ("persName", "Hegseth"): {"count": 2, "variants": ["Hegseth"]},
            ("persName", "Pete Hegseth"): {"count": 1, "variants": ["Pete Hegseth"]},
            ("persName", "Rubio"): {"count": 1, "variants": ["Rubio"]},
        }
        restore_original_variants(groups, result.replacements)
        assert groups[("persName", "Hegseth")]["variants"] == ["Hegseth", "Hekset", "Hexeta"]
        # The alias replacement is restored; "Pete Hekset"-style extras are harmless (never in the text).
        assert groups[("persName", "Pete Hegseth")]["variants"][:2] == ["Pete Hegseth", "He H"]
        assert groups[("persName", "Rubio")]["variants"] == ["Rubio"]

    def test_multiword_variant_is_restored_in_place(self):
        result = apply_glossary("Pete Hekset", [HEGSETH])
        groups = {("persName", "Pete Hegseth"): {"count": 1, "variants": ["Pete Hegseth"]}}
        restore_original_variants(groups, result.replacements)
        assert groups[("persName", "Pete Hegseth")]["variants"] == ["Pete Hegseth", "Pete Hekset"]
