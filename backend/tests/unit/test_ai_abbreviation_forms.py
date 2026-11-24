"""Closed-list AI normalization and original surface variants for highlighting."""

from collections import Counter

import pytest

from library.ai_abbreviation_forms import normalize_ai_forms
from library.ner_channel_glossary import restore_original_variants


@pytest.mark.parametrize("original", ["AIU", "AI-u", "AI-em", "AI-a", "AI-owi"])
def test_each_form_as_a_whole_word(original):
    normalized, replacements = normalize_ai_forms(f"{original}, ({original}).")
    assert normalized == "AI, (AI)."
    assert replacements == Counter({(None, original, "AI"): 2})


def test_document_11284_and_open_ai():
    original = "No ale czy to jest prawdziwe zdjęcie, czy zrobione w AIU, Photoshopie? Open AIU"
    normalized, replacements = normalize_ai_forms(original)
    assert normalized == "No ale czy to jest prawdziwe zdjęcie, czy zrobione w AI, Photoshopie? Open AI"
    assert replacements == Counter({(None, "AIU", "AI"): 2})


@pytest.mark.parametrize("text", [
    "RAIU", "AIUB", "aiu", "AI-up", "AI", "", "2AIU", "AIU2", "żAIU", "AIUą",
    "x-AIU", "AIU-x", "AI-u-p", "x-AI-em", "ai-u", "AI-OWI",
])
def test_unlisted_forms_and_word_fragments_are_unchanged(text):
    normalized, replacements = normalize_ai_forms(text)
    assert normalized == text
    assert isinstance(replacements, Counter)
    assert not replacements


def test_original_forms_restored_to_group_variants():
    _, replacements = normalize_ai_forms("AIU AI-u Open AIU")
    groups = {
        ("orgName", "AI"): {"count": 2, "variants": ["AI"]},
        ("orgName", "Open AI"): {"count": 1, "variants": ["Open AI"]},
    }
    restore_original_variants(groups, replacements)
    assert set(groups[("orgName", "AI")]["variants"]) == {"AI", "AIU", "AI-u"}
    assert "Open AIU" in groups[("orgName", "Open AI")]["variants"]
    assert replacements == Counter({(None, "AIU", "AI"): 2, (None, "AI-u", "AI"): 1})
