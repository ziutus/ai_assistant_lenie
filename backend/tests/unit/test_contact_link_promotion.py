import datetime
from unittest.mock import MagicMock

import pytest

from library.contact_link_promotion import link_type_for_lookup, promote_lookup_result
from library.db.models import Contact, ContactChangeLog, ContactLink, ContactLookupResult


@pytest.mark.parametrize("lookup_type,url,expected", [
    ("facebook", "https://www.facebook.com/radek.lejsza", "facebook"),
    ("web", "https://m.facebook.com/radek.lejsza", "facebook"),
    ("web", "https://www.instagram.com/x/", "instagram"),
    ("web", "https://x.com/someone", "twitter"),
    ("web", "https://www.linkedin.com/in/a/", "linkedin"),
    ("facebook", "https://example.com/profile", "facebook"),
    ("web", "https://example.com/about", None),
    ("phone", "https://example.com/", None),
    ("facebook", None, None),
])
def test_link_type_for_lookup(lookup_type, url, expected):
    assert link_type_for_lookup(lookup_type, url) == expected


def _session(existing):
    session = MagicMock()
    session.scalars.return_value = existing
    return session


def _row(lookup_type="web", url="https://www.facebook.com/radek.lejsza"):
    return ContactLookupResult(id=18, contact_id=396, lookup_type=lookup_type, status="confirmed", url=url)


def _added(session, model):
    return [c.args[0] for c in session.add.call_args_list if isinstance(c.args[0], model)]


def test_facebook_result_is_added_with_history_note():
    session = _session([])
    added = promote_lookup_result(
        session, Contact(id=396), _row(), confirmed_at=datetime.datetime(2026, 9, 14, 10, 19),
    )
    assert added is not None and added.link_type == "facebook" and added.url == _row().url
    (log,) = _added(session, ContactChangeLog)
    assert log.source == "osint_lookup" and log.changed_fields == ["links"]
    assert "#18" in log.note and "typ: web" in log.note and "2026-09-14" in log.note


def test_same_facebook_url_is_not_duplicated_even_with_www_and_trailing_slash():
    existing = ContactLink(id=1, contact_id=396, link_type="facebook", url="https://facebook.com/Radek.Lejsza/")
    session = _session([existing])
    assert promote_lookup_result(session, Contact(id=396), _row()) is None
    session.add.assert_not_called()


def test_different_facebook_url_is_added_next_to_existing_one():
    existing = ContactLink(id=1, contact_id=396, link_type="facebook", url="https://www.facebook.com/other")
    session = _session([existing])
    added = promote_lookup_result(session, Contact(id=396), _row())
    assert added is not None and existing.url == "https://www.facebook.com/other"


def test_profile_php_ids_are_distinct_profiles():
    existing = ContactLink(id=1, contact_id=396, link_type="facebook", url="https://www.facebook.com/profile.php?id=1")
    session = _session([existing])
    assert promote_lookup_result(
        session, Contact(id=396), _row(url="https://www.facebook.com/profile.php?id=2"),
    ) is not None
    assert promote_lookup_result(
        _session([existing]), Contact(id=396), _row(url="https://www.facebook.com/profile.php?id=1"),
    ) is None


def test_non_profile_result_is_ignored():
    session = _session([])
    assert promote_lookup_result(session, Contact(id=396), _row(url="https://example.com/x")) is None
    session.add.assert_not_called()
