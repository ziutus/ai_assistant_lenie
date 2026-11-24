"""Normalize Polish AI inflections on the text copy sent to NER.

Document #11284 contains STT's "AIU", incorrectly recognized as an organization.
The closed, case-sensitive list avoids guessing at other words or abbreviations.
Other meanings of "AIU" (for example a university) are deliberately out of scope.
The stored document text is never modified.
"""

import re
from collections import Counter


_AI_FORMS = re.compile(r"(?<![\w-])(?:AIU|AI-u|AI-em|AI-a|AI-owi)(?![\w-])")


def normalize_ai_forms(text: str) -> tuple[str, Counter]:
    """Return a normalized copy and counts compatible with restore_original_variants."""
    replacements = Counter()

    def replace(match: re.Match) -> str:
        replacements[(None, match.group(0), "AI")] += 1
        return "AI"

    return _AI_FORMS.sub(replace, text), replacements
