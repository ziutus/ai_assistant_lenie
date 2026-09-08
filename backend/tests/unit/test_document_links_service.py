"""Unit tests for library/document_links_service.py — pure helpers + the
URL-mention detector and create_link dedup logic against mocked sessions."""

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

pytest.importorskip("sqlalchemy")

from library import document_links_service as svc


# --- pure helpers -----------------------------------------------------------


def test_relations_have_two_labels_each():
    for key, value in svc.RELATIONS.items():
        assert isinstance(value, tuple) and len(value) == 2
        assert all(isinstance(part, str) and part for part in value)
    assert svc.SYMMETRIC_RELATIONS <= set(svc.RELATIONS)


def test_validate_relation_rejects_unknown():
    assert svc.validate_relation("discusses") == "discusses"
    with pytest.raises(svc.DocumentLinkError):
        svc.validate_relation("mentions")


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("https://github.com/sequelachi/poprawna-polszczyzna", "github.com/sequelachi/poprawna-polszczyzna"),
        ("http://www.GitHub.com/sequelachi/poprawna-polszczyzna/", "github.com/sequelachi/poprawna-polszczyzna"),
        ("github.com/sequelachi/poprawna-polszczyzna", "github.com/sequelachi/poprawna-polszczyzna"),
        ("https://example.com/a?b=1#frag", "example.com/a?b=1"),
        ("not a url", None),
        (None, None),
    ],
)
def test_normalize_url(raw, expected):
    assert svc._normalize_url(raw) == expected


def test_validate_note_trims_and_caps():
    assert svc._validate_note("  hello  ") == "hello"
    assert svc._validate_note("") is None
    with pytest.raises(svc.DocumentLinkError):
        svc._validate_note("x" * 501)


def test_link_to_dict_resolves_perspective():
    link = SimpleNamespace(
        id=5, relation="discusses", status="confirmed", detection_method="manual",
        note=None, from_document_id=10477, to_document_id=10474,
        created_at=None, decided_at=None,
        from_document=SimpleNamespace(id=10477, title="Post LinkedIn", url="https://linkedin.com/x",
                                      document_type="social_media_post", byline="Michał Kolasa",
                                      published_on=None),
        to_document=SimpleNamespace(id=10474, title="GitHub repo", url="https://github.com/x",
                                    document_type="link", byline=None, published_on=None),
    )
    from_view = svc.link_to_dict(link, perspective_document_id=10477)
    assert from_view["direction"] == "outgoing"
    assert from_view["label"] == "Omawia"
    assert from_view["other_document"]["id"] == 10474

    to_view = svc.link_to_dict(link, perspective_document_id=10474)
    assert to_view["direction"] == "incoming"
    assert to_view["label"] == "Omawiane w"
    assert to_view["other_document"]["id"] == 10477


# --- create_link -----------------------------------------------------------


def _session_with(docs, existing_link=None):
    session = MagicMock()
    session.scalars.side_effect = [MagicMock(all=lambda: docs)]
    session.scalar.return_value = existing_link
    return session


def test_create_link_rejects_self_link():
    with pytest.raises(svc.DocumentLinkError):
        svc.create_link(MagicMock(), 1, 1, "related")


def test_create_link_rejects_unknown_document():
    session = _session_with([SimpleNamespace(id=1)])
    with pytest.raises(svc.DocumentLinkError):
        svc.create_link(session, 1, 2, "related", commit=False)


def test_create_link_adds_row():
    session = _session_with([SimpleNamespace(id=1), SimpleNamespace(id=2)])
    link = svc.create_link(session, 1, 2, "discusses", note="  bo tak ", commit=False)
    assert link.from_document_id == 1
    assert link.to_document_id == 2
    assert link.relation == "discusses"
    assert link.note == "bo tak"
    assert link.status == "confirmed"
    session.add.assert_called_once()


def test_create_link_url_mention_keeps_existing_untouched():
    existing = SimpleNamespace(status="rejected", detection_method="url_mention")
    session = _session_with([SimpleNamespace(id=1), SimpleNamespace(id=2)], existing_link=existing)
    link = svc.create_link(
        session, 1, 2, "references", status="proposed",
        detection_method="url_mention", commit=False,
    )
    assert link is existing
    assert link.status == "rejected"
    session.add.assert_not_called()


# --- detect_url_mention_links --------------------------------------------------


def test_detect_url_mention_links_matches_bare_domain():
    doc = SimpleNamespace(
        id=10477, url="https://linkedin.com/feed/x", canonical_url="https://linkedin.com/feed/x",
        text_md=None, text="Wrzuciłem na GitHuba: github.com/sequelachi/poprawna-polszczyzna 😊",
        summary=None,
    )
    other = SimpleNamespace(
        id=10474, url="https://github.com/sequelachi/poprawna-polszczyzna",
        canonical_url="https://github.com/sequelachi/poprawna-polszczyzna",
    )
    session = MagicMock()
    session.get.return_value = doc
    # 1st scalars() -> candidates by ILIKE; then create_link's document lookup;
    # scalar() -> no existing edge.
    session.scalars.side_effect = [
        MagicMock(all=lambda: [other]),
    ]
    session.scalar.return_value = None

    created = svc.detect_url_mention_links(session, 10477, commit=False)
    assert len(created) == 1
    assert created[0].to_document_id == 10474
    assert created[0].relation == "references"
    assert created[0].status == "proposed"
    assert created[0].detection_method == "url_mention"


def test_detect_url_mention_links_no_urls_returns_empty():
    doc = SimpleNamespace(id=1, url="https://x.test", canonical_url="https://x.test",
                          text_md="brak linków tutaj", text=None, summary=None)
    session = MagicMock()
    session.get.return_value = doc
    assert svc.detect_url_mention_links(session, 1, commit=False) == []
