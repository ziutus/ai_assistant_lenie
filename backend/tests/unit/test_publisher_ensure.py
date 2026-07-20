"""Unit tests for Publisher.ensure() and Document.set_publisher_from_url()."""

from unittest.mock import MagicMock

from library.db import models


class TestPublisherEnsure:
    def test_returns_existing_row(self):
        session = MagicMock()
        existing_publisher = models.Publisher(canonical_name="wp.pl")
        existing_domain = models.PublisherDomain(domain="wp.pl", publisher=existing_publisher)
        session.execute.return_value.scalar_one_or_none.return_value = existing_domain

        assert models.Publisher.ensure(session, "wp.pl") is existing_publisher
        session.add.assert_not_called()

    def test_creates_missing_row(self):
        session = MagicMock()
        session.execute.return_value.scalar_one_or_none.return_value = None

        publisher = models.Publisher.ensure(session, "wp.pl")

        assert publisher.canonical_name == "wp.pl"
        added = [call.args[0] for call in session.add.call_args_list]
        assert publisher in added
        domain_rows = [row for row in added if isinstance(row, models.PublisherDomain)]
        assert len(domain_rows) == 1
        assert domain_rows[0].domain == "wp.pl"
        assert domain_rows[0].publisher is publisher

    def test_reuses_pending_row_before_flush(self):
        pending_publisher = models.Publisher(canonical_name="wp.pl")
        pending_domain = models.PublisherDomain(domain="wp.pl", publisher=pending_publisher)
        session = MagicMock()
        session.new = [pending_domain]

        assert models.Publisher.ensure(session, "wp.pl") is pending_publisher
        session.execute.assert_not_called()
        session.add.assert_not_called()

    def test_empty_domain_returns_none(self):
        session = MagicMock()
        assert models.Publisher.ensure(session, "   ") is None
        session.execute.assert_not_called()

    def test_domain_is_normalized_before_lookup(self):
        session = MagicMock()
        session.execute.return_value.scalar_one_or_none.return_value = None
        publisher = models.Publisher.ensure(session, "  WWW.WP.PL. ")
        assert publisher.canonical_name == "wp.pl"


class TestSetPublisherFromUrl:
    def _session(self, existing_publisher=None):
        session = MagicMock()
        if existing_publisher is not None:
            existing_domain = models.PublisherDomain(domain="wp.pl", publisher=existing_publisher)
            session.execute.return_value.scalar_one_or_none.return_value = existing_domain
        else:
            session.execute.return_value.scalar_one_or_none.return_value = None
        return session

    def test_auto_creates_publisher_for_unknown_domain(self):
        doc = models.Document(url="https://tech.wp.pl/artykul", document_type="link")
        session = self._session()
        doc.set_publisher_from_url(session)
        assert doc.publisher is not None
        assert doc.publisher.canonical_name == "wp.pl"

    def test_merges_multi_section_site_into_the_same_publisher(self):
        existing = models.Publisher(canonical_name="wp.pl")
        session = self._session(existing_publisher=existing)
        doc = models.Document(url="https://wiadomosci.wp.pl/news", document_type="link")
        doc.set_publisher_from_url(session)
        assert doc.publisher is existing

    def test_gmail_synthetic_url_gets_no_publisher(self):
        # email_import.py's url = f"gmail://{msg_id}" must never be misparsed as a hostname.
        doc = models.Document(url="gmail://0192abcd", document_type="email")
        session = self._session()
        doc.set_publisher_from_url(session)
        assert doc.publisher is None
        session.execute.assert_not_called()

    def test_explicit_url_overrides_self_url(self):
        doc = models.Document(url="https://placeholder.example", document_type="link")
        session = self._session()
        doc.set_publisher_from_url(session, url="https://knf.gov.pl/ostrzezenia")
        assert doc.publisher.canonical_name == "knf.gov.pl"
