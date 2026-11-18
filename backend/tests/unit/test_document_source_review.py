"""Ignoring a timeline proposal that is no event, and reviewing the information sources of a document.

Shares its in-memory SQLite fixture with ``test_document_event_sources``.
"""

from types import SimpleNamespace

import pytest

pytest.importorskip("sqlalchemy")
pytest.importorskip("flask")

from flask import Flask
from sqlalchemy import select

from library import document_event_sources as des
from library import document_source_review as review
from library import timeline_events
from library import world_events_routes as we_routes
from library.db.models import DocumentEvent, DocumentInformationSource, InformationSource
from library.geopolitics_service import GeopoliticsError
from tests.unit.geo_sqlite_support import add_document_event
from tests.unit.test_document_event_sources import TOWERS, session  # noqa: F401  (fixture)

PIRATES = "To jest symbol XIX wieku, XVIII, XIX wieku. Używany przez piratów notabene."


# --- ignoring a proposal --------------------------------------------------------------------------------------


def test_the_same_passage_is_recognised_whatever_the_cut():
    ignored = [timeline_events.passage_key(PIRATES)]

    assert timeline_events.is_ignored_passage({"anchor_quote": PIRATES.upper()}, ignored)
    assert timeline_events.is_ignored_passage({"anchor_quote": "symbol XIX wieku, XVIII, XIX wieku"}, ignored)
    assert not timeline_events.is_ignored_passage({"anchor_quote": "W 2018 roku w Parkland zginęło 17 osób."}, ignored)
    # a few words two sentences have in common are not "the same passage"
    assert not timeline_events.is_ignored_passage({"anchor_quote": "XIX wieku"}, ignored)
    assert not timeline_events.is_ignored_passage({"anchor_quote": ""}, ignored)


def test_ignoring_marks_the_row_and_restoring_clears_it(session):  # noqa: F811
    add_document_event(session, 10, 1, "XIX wiek - okres użycia symbolu piratów", "1801-01-01", precision="year")
    session.commit()

    assert des.set_document_event_ignored(session, 10, True)["ignored"] is True
    assert session.get(DocumentEvent, 10).ignored_at is not None
    assert des.set_document_event_ignored(session, 10, False)["ignored"] is False
    assert session.get(DocumentEvent, 10).ignored_at is None
    with pytest.raises(GeopoliticsError):
        des.set_document_event_ignored(session, 999, True)


def test_a_new_detection_keeps_the_dismissed_proposal_and_does_not_bring_its_passage_back(session, monkeypatch):  # noqa: F811
    add_document_event(session, 10, 1, "XIX wiek - symbol piratów", "1801-01-01", precision="year")
    add_document_event(session, 11, 1, "Stara propozycja", "2010-01-01", precision="year")
    session.commit()
    session.get(DocumentEvent, 10).anchor_quote = PIRATES
    des.set_document_event_ignored(session, 10, True)
    session.commit()

    fresh = {
        "model": "m",
        "events": [
            {"chapter_position": 1, "date_text": "XIX wieku", "description": "Okres użycia symbolu piratów",
             "anchor_quote": "symbol XIX wieku, XVIII, XIX wieku", "event_date": None, "event_date_end": None,
             "date_precision": "century", "sort_year": 1850},
            {"chapter_position": 1, "date_text": "2018", "description": "Strzelanina w Parkland",
             "anchor_quote": "W 2018 roku w Parkland zginęło 17 osób.", "event_date": None, "event_date_end": None,
             "date_precision": "year", "sort_year": 2018},
        ],
        "publication_sources": [],
        "chapters": [],
    }
    monkeypatch.setattr(timeline_events, "extract_document_events", lambda *_a, **_k: fresh)

    result = timeline_events.refresh_document_events(session, SimpleNamespace(id=1, enrichment_run_at=None))
    session.commit()

    assert result["skipped_ignored"] == 1
    assert session.get(DocumentEvent, 10).ignored_at is not None
    descriptions = {row.description for row in session.scalars(select(DocumentEvent)).all()}
    assert descriptions == {"XIX wiek - symbol piratów", "Strzelanina w Parkland"}


@pytest.fixture
def client(session, monkeypatch):  # noqa: F811
    from library import document_sources_routes as ds_routes

    monkeypatch.setattr(we_routes, "get_scoped_session", lambda: session)
    monkeypatch.setattr(ds_routes, "get_scoped_session", lambda: session)
    app = Flask(__name__)
    app.register_blueprint(we_routes.bp)
    app.register_blueprint(ds_routes.bp)
    return app.test_client()


def test_ignore_endpoint_toggles_the_flag(client, session):  # noqa: F811
    add_document_event(session, 10, 1, "XIX wiek - symbol piratów", "1801-01-01", precision="year")
    session.commit()

    assert client.post("/document_events/10/ignore", json={}).get_json()["ignored"] is True
    assert client.post("/document_events/10/ignore", json={"ignored": False}).get_json()["ignored"] is False
    assert client.post("/document_events/999/ignore", json={}).status_code == 404


# --- reviewing a source of a document -------------------------------------------------------------------------


def _link(session, document_id=1, name="Badanie Towers", role="cited", status="needs_review",  # noqa: F811
          organization_id=None):
    source = InformationSource(canonical_name=name, source_type="study", organization_id=organization_id)
    session.add(source)
    session.flush()
    link = DocumentInformationSource(
        document_id=document_id, source_id=source.id, role=role, raw_mention=name, confidence=70,
        extraction_method="timeline_publication", review_status=status,
    )
    session.add(link)
    session.commit()
    return link


def test_a_source_used_only_here_is_renamed_in_place_and_approved(session):  # noqa: F811
    link = _link(session)

    entry = review.update_document_source_link(session, 1, link.id, {"name": "Towers i in. (2015)"})
    session.commit()

    assert entry["canonical_name"] == "Towers i in. (2015)" and entry["review_status"] == "approved"
    assert len(session.scalars(select(InformationSource)).all()) == 1


def test_a_shared_source_is_not_renamed_under_the_other_document(session):  # noqa: F811
    first = _link(session, document_id=1)
    second = DocumentInformationSource(
        document_id=2, source_id=first.source_id, role="cited", raw_mention="x", extraction_method="llm",
        review_status="auto_accepted",
    )
    session.add(second)
    session.commit()

    review.update_document_source_link(session, 1, first.id, {"name": "Towers 2015"})
    session.commit()

    names = {s.canonical_name for s in session.scalars(select(InformationSource)).all()}
    assert names == {"Badanie Towers", "Towers 2015"}
    assert session.get(DocumentInformationSource, second.id).source.canonical_name == "Badanie Towers"


def test_renaming_to_an_existing_source_links_to_it_and_drops_the_orphan(session):  # noqa: F811
    keep = _link(session, document_id=2, name="Towers 2015")
    mine = _link(session, document_id=1, name="Badanie Towers (zła nazwa)")

    entry = review.update_document_source_link(session, 1, mine.id, {"name": "towers 2015"})
    session.commit()

    assert entry["source_id"] == keep.source_id
    assert [s.canonical_name for s in session.scalars(select(InformationSource)).all()] == ["Towers 2015"]


def test_an_organization_source_cannot_be_renamed_here_and_bad_input_is_rejected(session):  # noqa: F811
    org_link = _link(session, name="WHO", organization_id=1)
    plain = _link(session, name="Raport X", role="data_source")

    for link_id, body, status in [
        (org_link.id, {"name": "Światowa Organizacja Zdrowia"}, 400),
        (plain.id, {"source_type": "podcast"}, 400),
        (plain.id, {"role": "publisher"}, 400),
        (plain.id, {"review_status": "maybe"}, 400),
        (plain.id, {"name": ""}, 400),
        (99999, {"name": "x"}, 404),
    ]:
        with pytest.raises(GeopoliticsError) as error:
            review.update_document_source_link(session, 1, link_id, body)
        assert error.value.status == status
    with pytest.raises(GeopoliticsError) as wrong_document:
        review.update_document_source_link(session, 2, plain.id, {"name": "x"})
    assert wrong_document.value.status == 404


def test_changing_the_role_to_one_already_present_is_a_conflict(session):  # noqa: F811
    link = _link(session, role="cited")
    session.add(DocumentInformationSource(
        document_id=1, source_id=link.source_id, role="data_source", raw_mention="x", extraction_method="llm",
    ))
    session.commit()

    with pytest.raises(GeopoliticsError) as error:
        review.update_document_source_link(session, 1, link.id, {"role": "data_source"})

    assert error.value.status == 409


def test_a_rejected_publication_is_not_proposed_again(session):  # noqa: F811
    link = _link(session, name=des.default_source_name(TOWERS))
    review.update_document_source_link(session, 1, link.id, {"review_status": "rejected"})
    session.commit()

    again = des.save_detected_publications(session, 1, [{"description": TOWERS, "anchor_quote": "x"}])

    assert again == []
    assert session.get(DocumentInformationSource, link.id).review_status == "rejected"


def test_patch_endpoint_returns_the_entry_and_maps_errors(client, session):  # noqa: F811
    link = _link(session)

    ok = client.patch(f"/document/1/information_sources/{link.id}", json={"review_status": "approved"})
    assert ok.status_code == 200 and ok.get_json()["entry"]["review_status"] == "approved"
    assert client.patch(f"/document/1/information_sources/{link.id}", json={"role": "x"}).status_code == 400
    assert client.patch("/document/1/information_sources/99999", json={"name": "a"}).status_code == 404
    assert client.patch(f"/document/1/information_sources/{link.id}", data="nie json").status_code == 400
