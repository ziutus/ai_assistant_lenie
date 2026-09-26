"""Promote a confirmed OSINT lookup result into the contact's `contact_links`.

`contact_lookup_results` keeps the search trail (evidence); `contact_links` is
the section the user actually reads. Shared by the REST confirm path
(`contact_routes.contact_lookup_results_update`) and the backfill
(`imports/backfill_confirmed_lookup_links.py`).
"""

import datetime
from urllib.parse import urlparse

from sqlalchemy import select

from library.contact_change_log import record_contact_change
from library.db.models import Contact, ContactLink, ContactLookupResult

_HOST_TO_LINK_TYPE = {
    "facebook.com": "facebook", "fb.com": "facebook", "fb.me": "facebook",
    "instagram.com": "instagram",
    "twitter.com": "twitter", "x.com": "twitter",
    "linkedin.com": "linkedin",
}
_LOOKUP_TYPE_DEFAULT = {"linkedin": "linkedin", "facebook": "facebook"}
_LINK_TYPE_LABEL = {"linkedin": "LinkedIn", "facebook": "Facebook", "instagram": "Instagram", "twitter": "Twitter/X"}


def _host(url: str) -> str:
    host = (urlparse(url if "://" in url else f"https://{url}").hostname or "").lower()
    for prefix in ("www.", "m.", "pl-pl.", "mobile."):
        if host.startswith(prefix):
            host = host[len(prefix):]
    return host


def link_type_for_lookup(lookup_type: str, url: str | None) -> str | None:
    """Social link type for a lookup result, or None when it is not a profile link
    (phone/email, or a generic `web` hit on an unknown host)."""
    if not url:
        return None
    by_host = _HOST_TO_LINK_TYPE.get(_host(url))
    if by_host:
        return by_host
    return _LOOKUP_TYPE_DEFAULT.get(lookup_type)


def _normalize_url(url: str) -> str:
    parsed = urlparse(url if "://" in url else f"https://{url}")
    # profile.php identifies the profile only through its `id` query parameter.
    query = f"?{parsed.query.lower()}" if parsed.path.endswith("profile.php") else ""
    return f"{_host(url)}{parsed.path.rstrip('/').lower()}{query}"


def promote_lookup_result(
    session, contact: Contact, row: ContactLookupResult, *, confirmed_at: datetime.datetime | None = None,
) -> ContactLink | None:
    """Add (or, for LinkedIn, update) the contact link for a confirmed lookup result and
    log where it came from. Returns the added link, or None when nothing was added."""
    link_type = link_type_for_lookup(row.lookup_type, row.url)
    if link_type is None:
        return None

    links = list(session.scalars(select(ContactLink).where(
        ContactLink.contact_id == contact.id, ContactLink.link_type == link_type,
    ).order_by(ContactLink.id)))
    if any(_normalize_url(link.url) == _normalize_url(row.url) for link in links):
        return None

    if link_type == "linkedin":
        # A person has one LinkedIn profile: the confirmed result replaces the old URL.
        added = None
        if links:
            links[0].url = row.url
        else:
            added = ContactLink(contact_id=contact.id, link_type="linkedin", url=row.url)
            session.add(added)
        record_contact_change(
            session, contact, "linkedin_analysis", changed_fields=["links"],
            note=f"Potwierdzony wynik OSINT (lookup #{row.id})",
        )
        return added

    added = ContactLink(contact_id=contact.id, link_type=link_type, url=row.url)
    session.add(added)
    when = (confirmed_at or datetime.datetime.now()).strftime("%Y-%m-%d")
    record_contact_change(
        session, contact, "osint_lookup", changed_fields=["links"],
        note=(
            f"Link {_LINK_TYPE_LABEL.get(link_type, link_type)} przeniesiony z wyników wyszukiwania OSINT "
            f"(lookup #{row.id}, typ: {row.lookup_type}), potwierdzony {when}"
        ),
    )
    return added
