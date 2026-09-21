from library.whatsapp_parser import strip_sender_suffix


def test_strip_sender_suffix_removes_trailing_tag():
    assert strip_sender_suffix("Kacper Drużbicki - Tuwima Gardens", "Tuwima Gardens") == "Kacper Drużbicki"


def test_strip_sender_suffix_case_insensitive_and_spacing():
    assert strip_sender_suffix("Wojtek Szot -tuwima gardens", "Tuwima Gardens") == "Wojtek Szot"


def test_strip_sender_suffix_no_suffix_configured_returns_unchanged():
    assert strip_sender_suffix("Kacper Drużbicki - Tuwima Gardens", None) == "Kacper Drużbicki - Tuwima Gardens"
    assert strip_sender_suffix("Kacper Drużbicki - Tuwima Gardens", "") == "Kacper Drużbicki - Tuwima Gardens"


def test_strip_sender_suffix_no_match_returns_unchanged():
    assert strip_sender_suffix("+48 668 527 645", "Tuwima Gardens") == "+48 668 527 645"


def test_strip_sender_suffix_only_strips_trailing_occurrence():
    assert strip_sender_suffix("Tuwima Gardens - Kacper Drużbicki", "Tuwima Gardens") == "Tuwima Gardens - Kacper Drużbicki"
