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


def test_apply_footer_rule_allows_only_footer_url_values_to_change():
    session = _Session(
        "Brand (https://old.click.example/campaign/recipient)\n"
        "Unsubscribe (https://old.unsubscribe.example/campaign/recipient)\n"
        "Copyright Brand"
    )
    text = (
        "Newsletter body\n\n"
        "Brand (https://new.click.example/new-campaign/new-recipient)\n"
        "Unsubscribe (https://new.unsubscribe.example/new-campaign/new-recipient)\n"
        "Copyright Brand\n"
    )
    assert apply_footer_rule(session, "sender@example.com", text) == "Newsletter body"


def test_apply_footer_rule_does_not_match_changed_non_url_footer_text():
    session = _Session("Brand (https://old.example/a)\nAddress Warsaw")
    text = "Body\nBrand (https://new.example/b)\nAddress Krakow"
    assert apply_footer_rule(session, "sender@example.com", text) == text
