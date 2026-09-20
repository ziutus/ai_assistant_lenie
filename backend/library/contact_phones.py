"""Conservative phone normalization for the Polish private contact book.

Only valid numbers are canonicalized. Service codes, short numbers and unknown
text survive unchanged and must never identify a person during import.
"""
import re

import phonenumbers

_PHONE = re.compile(r"(?P<number>\+?[0-9\s().-]+?)(?:\s*(?:ext\.?|x|wew\.?)\s*(?P<extension>[0-9]+))?", re.I)


def phone_identity_key(value: str) -> str | None:
    match = _PHONE.fullmatch(value.strip())
    if not match:
        return None
    number = re.sub(r"[\s().-]", "", match["number"])
    # Do not guess a country from a foreign national number or a bare country code.
    if not number.startswith(("+", "00")) and len(number) != 9:
        return None
    try:
        parsed = phonenumbers.parse(number, "PL")
    except phonenumbers.NumberParseException:
        return None
    if not phonenumbers.is_valid_number(parsed):
        return None
    canonical = phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164)
    if match["extension"]:
        canonical += " ext. " + match["extension"]
    return canonical if len(canonical) <= 30 else None


def normalize_phone(value: str) -> str:
    return phone_identity_key(value) or value.strip()


def phone_comparison_key(value: str) -> str:
    """Also deduplicate service/unknown entries, without trusting their identity."""
    return phone_identity_key(value) or re.sub(r"[\s().-]", "", value.strip()).casefold()


def phone_search_digits(value: str) -> str | None:
    """Numeric search fragments, not identity keys; never rewrite text queries."""
    if not re.fullmatch(r"\+?[0-9\s().-]+", value.strip()):
        return None
    digits = re.sub(r"[^0-9]", "", value)
    if value.strip().startswith("00"):
        digits = digits[2:]
    return digits or None
