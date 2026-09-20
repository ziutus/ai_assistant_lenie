import pytest

from library.contact_channels import channel_key, channel_patch, normalize_channels
from library.contact_phones import normalize_phone, phone_identity_key, phone_search_digits


@pytest.mark.parametrize("value", ["501234567", "501 234 567", "+48 501-234-567", "0048 (501) 234 567", "501\u00a0234\u00a0567"])
def test_polish_variants_share_canonical_value_and_key(value):
    assert normalize_phone(value) == "+48501234567"
    assert channel_key(value, "phone_numbers") == "+48501234567"


@pytest.mark.parametrize("raw,expected", [
    ("22 123 45 67", "+48221234567"), ("+44 20 8366 1177", "+442083661177"),
    ("0044 20 8366 1177", "+442083661177"), ("+1 (650) 253-2222", "+16502532222"),
    ("+39 02 3661 8300", "+390236618300"),
    ("22 123 45 67 wew. 12", "+48221234567 ext. 12"),
])
def test_international_fixed_line_and_extension(raw, expected):
    assert normalize_phone(raw) == expected


@pytest.mark.parametrize("raw", ["112", "*123#", "Poczta głosowa", "123", "48501234567", "020 8366 1177", "+999123456789", "abc501234567", "501234567/502234567"])
def test_service_invalid_and_ambiguous_numbers_are_preserved_but_not_identity(raw):
    assert normalize_phone(raw) == raw
    assert phone_identity_key(raw) is None


def test_extensions_are_distinct_identities():
    assert phone_identity_key("22 123 45 67 wew. 12") != phone_identity_key("22 123 45 67 wew. 13")
    assert phone_identity_key("22 123 45 67") != phone_identity_key("22 123 45 67 wew. 12")


def test_api_rejects_duplicate_formats_and_accepts_equivalent_primary():
    with pytest.raises(ValueError, match="duplicate"):
        normalize_channels([{"value": "501234567"}, {"value": "+48 501 234 567"}], "phone_numbers")
    assert channel_patch({"phone_number": "0048 501234567", "phone_numbers": [{"value": "501-234-567"}]}) == {
        "phone_number": "+48501234567", "phone_numbers": [{"value": "+48501234567", "label": None}]}


def test_legacy_update_uses_canonical_primary():
    assert channel_patch({"phone_number": "501 234 567"})["phone_number"] == "+48501234567"


@pytest.mark.parametrize("value,expected", [("0048 501-234-567", "48501234567"),
    ("+48 (501) 234 567", "48501234567"), ("501 234", "501234"),
    ("Jan 123", None), ("*123#", None), ("00", None)])
def test_numeric_search_keeps_text_queries_intact(value, expected):
    assert phone_search_digits(value) == expected
