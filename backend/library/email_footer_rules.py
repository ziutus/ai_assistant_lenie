"""Safe, sender-specific removal of manually approved email footers."""

from __future__ import annotations

from email.utils import parseaddr

from sqlalchemy import select
from sqlalchemy.orm import Session

from library.db.models import EmailFooterRule


def normalize_sender_email(value: str | None) -> str | None:
    """Return a lowercase bare address, or ``None`` for an invalid value."""
    _display_name, address = parseaddr(value or "")
    address = address.strip().lower()
    return address if "@" in address and "." in address.rsplit("@", 1)[-1] else None


def apply_footer_rule(session: Session, sender_email: str | None, text: str) -> str:
    """Remove only an exact footer at the end; never remove a mid-message match."""
    sender = normalize_sender_email(sender_email)
    if not sender or not text:
        return text
    rule = session.scalar(select(EmailFooterRule).where(EmailFooterRule.sender_email == sender))
    if rule is None:
        return text
    footer = rule.footer_text.strip()
    candidate = text.rstrip()
    if footer and candidate.endswith(footer):
        return candidate[:-len(footer)].rstrip()
    return text
