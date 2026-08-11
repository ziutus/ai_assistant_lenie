from types import SimpleNamespace

from library.email_footer_rules import apply_footer_rule, normalize_sender_email


class _Session:
    def __init__(self, footer_text: str | None):
        self.footer_text = footer_text

    def scalar(self, _statement):
        return SimpleNamespace(footer_text=self.footer_text) if self.footer_text else None


def test_normalize_sender_email_uses_address_not_display_name():
    assert normalize_sender_email("News Letter <NEWS@example.com>") == "news@example.com"
    assert normalize_sender_email("News Letter") is None


def test_apply_footer_rule_removes_only_exact_trailing_footer():
    session = _Session("Pozdrawiam,\nZespół Lenie")
    assert apply_footer_rule(session, "sender@example.com", "Treść\nPozdrawiam,\nZespół Lenie\n") == "Treść"
    assert apply_footer_rule(session, "sender@example.com", "Treść\nPozdrawiam,\nZespół Lenie\nDopisek") == (
        "Treść\nPozdrawiam,\nZespół Lenie\nDopisek"
    )
