"""Safe, sender-specific removal of manually approved email footers."""

from __future__ import annotations

from email.utils import parseaddr
import re

from sqlalchemy import select
from sqlalchemy.orm import Session

from library.db.models import EmailFooterRule


def normalize_sender_email(value: str | None) -> str | None:
    """Return a lowercase bare address, or ``None`` for an invalid value."""
    _display_name, address = parseaddr(value or "")
    address = address.strip().lower()
    return address if "@" in address and "." in address.rsplit("@", 1)[-1] else None


def apply_footer_rule(session: Session, sender_email: str | None, text: str) -> str:
    """Remove an approved trailing footer, allowing only its URLs to vary.

    Newsletter services commonly replace every link with a campaign- and
    recipient-specific redirect URL. The visible footer is otherwise stable,
    so a literal comparison would make a sender rule stop working for the next
    delivery. The fallback treats URLs in the approved footer as wildcards;
    every non-URL character must still match and the footer must be last.
    """
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
    if footer:
        match = _trailing_footer_with_variable_urls(footer, candidate)
        if match is not None:
            return candidate[:match.start()].rstrip()
    return text


_URL_RE = re.compile(r"https?://[^\s)]+", re.IGNORECASE)


def _trailing_footer_with_variable_urls(footer: str, text: str) -> re.Match[str] | None:
    """Match ``footer`` at the message end, with its URL values flexible."""
    parts: list[str] = []
    position = 0
    for url_match in _URL_RE.finditer(footer):
        parts.append(re.escape(footer[position:url_match.start()]))
        parts.append(r"https?://[^\s)]+")
        position = url_match.end()
    parts.append(re.escape(footer[position:]))
    if len(parts) == 1:
        return None
    return re.search("".join(parts) + r"\Z", text, re.IGNORECASE)
