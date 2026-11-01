"""Unit tests for library/geopolitics_service.py and geopolitics_detect.py (in-memory SQLite).

The exclusion constraint of the migration is PostgreSQL-only and is covered by the
integration test; here the service-level period logic is exercised.
"""

import datetime
from types import SimpleNamespace

import pytest

pytest.importorskip("sqlalchemy")

from sqlalchemy import JSON, DateTime, Integer, String, Text, create_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

from library import geopolitics_detect as detect
from library import geopolitics_service as svc
from library.db.engine import Base
from library.db.models import (
    Country,
    CountryRelationAssessment,
    CountryRelationEvidence,
    GeoEvent,
    GeoEventParticipant,
    GeoEventSource,
)


class _StubBase(DeclarativeBase):
    pass


class StubDocument(_StubBase):
    """Stands in for the real Document (pgvector columns cannot be created on SQLite)."""

    __tablename__ = "stub_documents"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(100), default="t")
    text_md: Mapped[str | None] = mapped_column(Text)
    text: Mapped[str | None] = mapped_column(Text)
    chapter_types: Mapped[list | None] = mapped_column(JSON)
    published_on: Mapped[datetime.date | None] = mapped_column(DateTime)
    ingested_at: Mapped[datetime.datetime | None] = mapped_column(DateTime)

    @classmethod
    def get_by_id(cls, session, doc_id):
        return session.get(cls, doc_id)


@pytest.fixture
def session(monkeypatch):
    engine = create_engine("sqlite://")
    Base.metadata.create_all(
        engine,
        tables=[
            Country.__table__,
            GeoEvent.__table__,
            GeoEventParticipant.__table__,
            GeoEventSource.__table__,
            CountryRelationAssessment.__table__,
            CountryRelationEvidence.__table__,
        ],
    )
    _StubBase.metadata.create_all(engine)
    monkeypatch.setattr(svc, "Document", StubDocument)
    monkeypatch.setattr(detect, "Document", StubDocument)
    monkeypatch.setattr(detect, "default_model", lambda session: "default-model")
    # The channel glossary reads tables SQLite does not have here; tests that need it patch it themselves.
    monkeypatch.setattr("library.entity_service.apply_channel_glossary_text", lambda session, document_id, text: text)
    monkeypatch.setattr(
        detect.prompt_templates, "get_active", lambda s, task, variant: detect.prompt_templates.builtin(task, variant)
    )
    with sessionmaker(bind=engine)() as s:
        for slug, name, code in [
            ("brazylia", "Brazylia", "BRA"),
            ("stany-zjednoczone", "Stany Zjednoczone", "USA"),
            ("turcja", "Turcja", "TUR"),
            ("kosowo", "Kosowo", "XKX"),
        ]:
            s.add(Country(slug=slug, name_pl=name, iso3=None if code == "XKX" else code, map_code=code))
        s.add(StubDocument(id=1, text_md="Opozycjonista uciekł do USA po wyborach w Brazylii."))
        s.commit()
        yield s


def _event(session, title="Ucieczka", date="2026-03-10", **kw):
    event, created = svc.create_event(
        session,
        title=title,
        event_date=date,
        participants=[("brazylia", "actor"), ("stany-zjednoczone", "target")],
        **kw,
    )
    session.commit()
    return event, created


# --- pure helpers -------------------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("2026-03-10", (datetime.date(2026, 3, 10), "day")),
        ("2026-03", (datetime.date(2026, 3, 1), "month")),
        ("2026", (datetime.date(2026, 1, 1), "year")),
    ],
)
def test_parse_event_date(raw, expected):
    assert svc.parse_event_date(raw) == expected


@pytest.mark.parametrize("raw", ["", "10.03.2026", "2026-13-01", None])
def test_parse_event_date_rejects(raw):
    with pytest.raises(svc.GeopoliticsError):
        svc.parse_event_date(raw)


@pytest.mark.parametrize("score", [3, -3, "1", 1.5, True, None])
def test_validate_score_rejects(score):
    with pytest.raises(svc.GeopoliticsError):
        svc.validate_score(score)


def test_every_axis_has_a_full_scale():
    for axis in svc.AXES.values():
        assert set(axis["scale"]) == {-2, -1, 0, 1, 2}


def test_add_months_clamps_day():
    assert svc._add_months(datetime.date(2026, 8, 31), 6) == datetime.date(2027, 2, 28)


# --- events -------------------------------------------------------------------


def test_create_event_resolves_slug_with_kraj_prefix(session):
    event, created = svc.create_event(
        session,
        title="X",
        event_date="2026-01-01",
        participants=[("kraj-turcja", "actor")],
    )
    assert created and event.participants[0].country.slug == "turcja"


def test_create_event_requires_known_country_and_role(session):
    with pytest.raises(svc.GeopoliticsError) as unknown:
        svc.create_event(session, title="X", event_date="2026", participants=[("atlantyda", "actor")])
    assert unknown.value.status == 404
    with pytest.raises(svc.GeopoliticsError):
        svc.create_event(session, title="X", event_date="2026", participants=[("turcja", "boss")])
    with pytest.raises(svc.GeopoliticsError):
        svc.create_event(session, title="X", event_date="2026", participants=[])


def test_repeated_report_adds_a_source_instead_of_a_second_event(session):
    first, created = _event(session, source={"document_id": 1, "quote": "Opozycjonista uciekł do USA"})
    second, created_again = _event(session, source={"document_id": 1, "quote": "po wyborach w Brazylii"})
    assert created and not created_again
    assert first.id == second.id
    assert len(second.sources) == 2
    assert session.query(GeoEvent).count() == 1


def test_same_source_quote_is_not_duplicated(session):
    _event(session, source={"document_id": 1, "quote": "Opozycjonista  uciekł do USA"})
    event, _ = _event(session, source={"document_id": 1, "quote": "opozycjonista uciekł do usa"})
    assert len(event.sources) == 1


def test_rejected_event_is_not_revived_by_a_new_report(session):
    event, _ = _event(session)
    svc.set_event_status(session, event, "rejected", None)
    session.commit()
    again, created = _event(session)
    assert not created and again.status == "rejected"


def test_source_needs_existing_document_and_quote(session):
    with pytest.raises(svc.GeopoliticsError) as missing:
        _event(session, title="Y", source={"document_id": 99, "quote": "cos"})
    assert missing.value.status == 404
    with pytest.raises(svc.GeopoliticsError):
        _event(session, title="Z", source={"document_id": 1, "quote": " "})


# --- assessments --------------------------------------------------------------


def _propose(session, score=-1, valid_from="2026-03-10", **kw):
    row = svc.create_assessment(
        session,
        from_country="brazylia",
        to_country="stany-zjednoczone",
        axis="political",
        score=score,
        valid_from=valid_from,
        **kw,
    )
    session.commit()
    return row


def test_assessment_validation(session):
    with pytest.raises(svc.GeopoliticsError):
        svc.create_assessment(
            session,
            from_country="turcja",
            to_country="turcja",
            axis="political",
            score=0,
            valid_from="2026",
        )
    with pytest.raises(svc.GeopoliticsError):
        _propose(session, score=5)
    with pytest.raises(svc.GeopoliticsError):
        svc.create_assessment(
            session,
            from_country="turcja",
            to_country="brazylia",
            axis="cultural",
            score=0,
            valid_from="2026",
        )
    with pytest.raises(svc.GeopoliticsError):
        _propose(session, event_ids=[404])


def test_single_event_confidence_is_capped(session):
    event, _ = _event(session)
    row = _propose(session, confidence=0.95, event_ids=[event.id])
    assert float(row.confidence) == svc.SINGLE_EVENT_CONFIDENCE_CAP


def test_two_events_from_one_article_stay_capped(session):
    first, _ = _event(session, source={"document_id": 1, "quote": "Opozycjonista uciekł do USA"})
    second, _ = _event(
        session, title="Sankcje", date="2026-04-01", source={"document_id": 1, "quote": "po wyborach w Brazylii"}
    )
    row = _propose(session, confidence=0.9, event_ids=[first.id, second.id])
    assert float(row.confidence) == svc.SINGLE_EVENT_CONFIDENCE_CAP


def test_reports_from_two_documents_may_exceed_the_cap(session):
    session.add(StubDocument(id=2, text_md="Inny artykuł."))
    session.commit()
    first, _ = _event(session, source={"document_id": 1, "quote": "Opozycjonista uciekł do USA"})
    second, _ = _event(session, title="Sankcje", date="2026-04-01", source={"document_id": 2, "quote": "Inny artykuł"})
    row = _propose(session, confidence=0.9, event_ids=[first.id, second.id])
    assert svc.independent_document_count(session, [first.id, second.id]) == 2
    assert float(row.confidence) == 0.9


def test_repeated_proposal_adds_evidence_instead_of_a_duplicate(session):
    first, _ = _event(session)
    second, _ = _event(session, title="Drugie", date="2026-03-10")
    kwargs = dict(
        from_country="brazylia", to_country="stany-zjednoczone", axis="political", score=-1, valid_from="2026-03-10"
    )
    row, created = svc.propose_assessment(session, event_ids=[first.id], **kwargs)
    again, created_again = svc.propose_assessment(session, event_ids=[first.id, second.id], **kwargs)
    session.commit()
    assert created and not created_again and row.id == again.id
    assert sorted(e.event_id for e in again.evidence) == sorted([first.id, second.id])
    assert session.query(CountryRelationAssessment).count() == 1


def test_a_different_score_for_the_same_start_stays_a_separate_proposal(session):
    first, _ = _event(session)
    kwargs = dict(from_country="brazylia", to_country="stany-zjednoczone", axis="political", valid_from="2026-03-10")
    svc.propose_assessment(session, score=-1, event_ids=[first.id], **kwargs)
    _, created = svc.propose_assessment(session, score=1, event_ids=[first.id], **kwargs)
    assert created and session.query(CountryRelationAssessment).count() == 2


def test_a_confirmed_assessment_does_not_absorb_a_new_proposal(session):
    _propose(session, score=-1, status="confirmed")
    event, _ = _event(session)
    _, created = svc.propose_assessment(
        session,
        from_country="brazylia",
        to_country="stany-zjednoczone",
        axis="political",
        score=-1,
        valid_from="2026-03-10",
        event_ids=[event.id],
    )
    assert created


def test_proposal_is_invisible_on_the_map_until_confirmed(session):
    _propose(session)
    brazil = svc.resolve_country(session, "brazylia")
    at = datetime.date(2026, 6, 1)
    assert svc.relations_at(session, country=brazil, at=at, axis="political", direction="from") == []


def test_confirming_closes_the_previous_open_period(session):
    old = _propose(session, score=1, valid_from="2025-01-01", status="confirmed")
    new = _propose(session, score=-1, valid_from="2026-03-10")
    svc.decide_assessment(session, new.id, decision="approve", expected_version=new.version, user_id=7)
    session.commit()
    session.refresh(old)
    assert old.valid_to == datetime.date(2026, 3, 10)
    assert new.status == "confirmed" and new.supersedes_id == old.id and new.decided_by_user_id == 7
    brazil = svc.resolve_country(session, "brazylia")
    before = svc.relations_at(session, country=brazil, at=datetime.date(2026, 3, 9), axis="political", direction="from")
    after = svc.relations_at(session, country=brazil, at=datetime.date(2026, 3, 10), axis="political", direction="from")
    assert [r["score"] for r in before] == [1]
    assert [r["score"] for r in after] == [-1]
    assert after[0]["other_country"]["slug"] == "stany-zjednoczone"


def test_direction_is_not_symmetric(session):
    _propose(session, score=-1, status="confirmed")
    usa = svc.resolve_country(session, "stany-zjednoczone")
    brazil = svc.resolve_country(session, "brazylia")
    at = datetime.date(2026, 6, 1)
    assert svc.relations_at(session, country=usa, at=at, axis="political", direction="from") == []
    toward_usa = svc.relations_at(session, country=usa, at=at, axis="political", direction="to")
    assert [r["other_country"]["slug"] for r in toward_usa] == ["brazylia"]
    assert svc.relations_at(session, country=brazil, at=at, axis="security", direction="from") == []


def test_axes_are_independent(session):
    _propose(session, score=-1, status="confirmed")
    svc.create_assessment(
        session,
        from_country="brazylia",
        to_country="stany-zjednoczone",
        axis="security",
        score=2,
        valid_from="2026-01-01",
        status="confirmed",
    )
    session.commit()
    brazil = svc.resolve_country(session, "brazylia")
    at = datetime.date(2026, 6, 1)
    assert svc.relations_at(session, country=brazil, at=at, axis="political", direction="from")[0]["score"] == -1
    assert svc.relations_at(session, country=brazil, at=at, axis="security", direction="from")[0]["score"] == 2


def test_backdated_change_before_a_confirmed_period_is_refused(session):
    _propose(session, score=1, valid_from="2026-03-10", status="confirmed")
    with pytest.raises(svc.GeopoliticsError) as exc:
        _propose(session, score=-1, valid_from="2026-01-01", status="confirmed")
    assert exc.value.status == 409


def test_same_start_date_conflicts(session):
    _propose(session, score=1, valid_from="2026-03-10", status="confirmed")
    with pytest.raises(svc.GeopoliticsError) as exc:
        _propose(session, score=0, valid_from="2026-03-10", status="confirmed")
    assert exc.value.status == 409


def test_stale_expected_version_is_a_conflict(session):
    row = _propose(session)
    with pytest.raises(svc.GeopoliticsError) as exc:
        svc.decide_assessment(session, row.id, decision="approve", expected_version=row.version + 5, user_id=None)
    assert exc.value.status == 409


def test_decided_assessment_cannot_be_decided_again(session):
    row = _propose(session)
    svc.decide_assessment(session, row.id, decision="reject", expected_version=None, user_id=None)
    with pytest.raises(svc.GeopoliticsError) as exc:
        svc.decide_assessment(session, row.id, decision="approve", expected_version=None, user_id=None)
    assert exc.value.status == 409


def test_approving_confirms_proposed_events_only_when_asked(session):
    event, _ = _event(session)
    keep, _ = _event(session, title="Inne", date="2026-04-01")
    row = _propose(session, event_ids=[event.id])
    svc.decide_assessment(session, row.id, decision="approve", expected_version=None, user_id=None)
    assert event.status == "confirmed" and keep.status == "proposed"

    event2, _ = _event(session, title="Trzecie", date="2026-05-01")
    row2 = _propose(session, score=0, valid_from="2026-05-01", event_ids=[event2.id])
    svc.decide_assessment(
        session, row2.id, decision="approve", expected_version=None, user_id=None, approve_events=False
    )
    assert event2.status == "proposed"


def test_rejected_proposal_never_reaches_the_map(session):
    row = _propose(session)
    svc.decide_assessment(session, row.id, decision="reject", expected_version=None, user_id=None)
    brazil = svc.resolve_country(session, "brazylia")
    assert (
        svc.relations_at(session, country=brazil, at=datetime.date(2027, 1, 1), axis="political", direction="from")
        == []
    )


def test_overdue_flag_after_review_date(session):
    row = _propose(session, status="confirmed")
    row.review_due_at = datetime.date(2026, 5, 1)
    assert svc.assessment_to_dict(row, today=datetime.date(2026, 6, 1))["overdue"] is True
    assert svc.assessment_to_dict(row, today=datetime.date(2026, 4, 1))["overdue"] is False


def test_proposals_list_shows_the_assessment_it_would_replace(session):
    _propose(session, score=1, valid_from="2025-01-01", status="confirmed")
    _propose(session, score=-1, valid_from="2026-03-10")
    proposals = svc.list_proposals(session)
    assert len(proposals) == 1
    assert proposals[0]["score"] == -1 and proposals[0]["current"]["score"] == 1


def test_history_lists_all_periods_of_the_pair_and_axis(session):
    first = _propose(session, score=1, valid_from="2025-01-01", status="confirmed")
    _propose(session, score=-1, valid_from="2026-03-10", status="confirmed")
    history = svc.assessment_history(session, first.id)
    assert [h["score"] for h in history] == [1, -1]
    assert history[0]["valid_to"] == "2026-03-10"


# --- detection ----------------------------------------------------------------


TEXT = "Opozycjonista uciekł do USA po wyborach w Brazylii. Rząd Brazylii zaprotestował."


def _fake_llm(monkeypatch, payload):
    import json

    calls = []

    def fake(prompt, **kwargs):
        calls.append((prompt, kwargs))
        return SimpleNamespace(response_text=json.dumps(payload) if not isinstance(payload, str) else payload)

    monkeypatch.setattr(detect, "ai_ask", fake)
    return calls


def _candidate(**over):
    item = {
        "title": "Opozycjonista uciekł do USA",
        "description": "Po wyborach przeciwnik prezydenta wyjechał do Stanów.",
        "date": "2026-03-10",
        "quote": "Opozycjonista uciekł do USA po wyborach",
        "participants": [{"country": "brazylia", "role": "actor"}, {"country": "stany-zjednoczone", "role": "target"}],
        "relation": None,
    }
    item.update(over)
    return item


@pytest.fixture
def doc(session, monkeypatch):
    session.get(StubDocument, 1).text_md = TEXT
    session.commit()
    monkeypatch.setattr(
        detect,
        "detect_countries",
        lambda text: [SimpleNamespace(slug="brazylia"), SimpleNamespace(slug="stany-zjednoczone")],
    )


def test_detect_stores_event_as_proposal_without_relation(session, doc, monkeypatch):
    calls = _fake_llm(monkeypatch, [_candidate()])
    out = detect.detect_for_document(session, 1, model="m")
    session.commit()
    assert out["events_created"] == 1 and out["assessments_proposed"] == 0
    event = session.get(GeoEvent, out["event_ids"][0])
    assert event.status == "proposed" and event.detection_method == "llm" and event.model == "m"
    assert event.sources[0].document_id == 1
    assert calls[0][1]["operation"] == "geopolitics_event_extraction"
    assert "brazylia" in calls[0][0]


def test_detect_one_event_relation_is_proposed_with_capped_confidence(session, doc, monkeypatch):
    relation = {"from": "brazylia", "to": "stany-zjednoczone", "axis": "political", "score": -1, "confidence": 0.99}
    _fake_llm(monkeypatch, [_candidate(relation=relation)])
    out = detect.detect_for_document(session, 1)
    session.commit()
    assert out["assessments_proposed"] == 1
    row = session.get(CountryRelationAssessment, out["assessment_ids"][0])
    assert row.status == "proposed" and float(row.confidence) == svc.SINGLE_EVENT_CONFIDENCE_CAP
    assert row.valid_from == datetime.date(2026, 3, 10)
    assert [e.event_id for e in row.evidence] == out["event_ids"]


def test_detect_rejects_hallucinated_quote(session, doc, monkeypatch):
    _fake_llm(monkeypatch, [_candidate(quote="Prezydent ogłosił wojnę całemu światu dzisiaj")])
    out = detect.detect_for_document(session, 1)
    assert out["events_created"] == 0 and out["rejected"]["quote_not_found"] == 1


def test_detect_rejects_bad_date_unknown_country_and_foreign_relation(session, doc, monkeypatch):
    foreign = {"from": "turcja", "to": "stany-zjednoczone", "axis": "political", "score": 1}
    _fake_llm(
        monkeypatch,
        [
            _candidate(date="wczoraj"),
            _candidate(title="Inne", participants=[{"country": "atlantyda", "role": "actor"}]),
            _candidate(title="Trzecie", relation=foreign),
        ],
    )
    out = detect.detect_for_document(session, 1)
    assert out["rejected"]["bad_date"] == 1
    assert out["rejected"]["bad_participants"] == 1
    assert out["rejected"]["bad_relation"] == 1
    assert out["events_created"] == 1 and out["assessments_proposed"] == 0


def test_relative_date_falls_back_to_the_article_date_with_a_note(session, doc, monkeypatch):
    session.get(StubDocument, 1).ingested_at = datetime.datetime(2026, 10, 27, 12, 0)
    session.commit()
    calls = _fake_llm(
        monkeypatch,
        [
            _candidate(date="obecnie", date_text="obecnie"),
            _candidate(title="Inne", date=None, date_text="od stycznia"),
            _candidate(title="Trzecie", date="2026-09"),
        ],
    )
    out = detect.detect_for_document(session, 1)
    session.commit()
    assert out["rejected"]["bad_date"] == 0 and out["events_created"] == 3 and out["dated_from_reference"] == 2
    assert "2026-10-27" in calls[0][0]
    events = {e.title: e for e in session.query(GeoEvent).all()}
    relative = events["Opozycjonista uciekł do USA"]
    assert relative.event_date == datetime.date(2026, 10, 27) and relative.date_precision == "month"
    assert "Data w tekście: „obecnie”" in relative.description
    assert events["Inne"].description.endswith("„od stycznia”; przyjęto datę artykułu.")
    assert events["Trzecie"].event_date == datetime.date(2026, 9, 1) and "przyjęto" not in (
        events["Trzecie"].description or ""
    )


def test_published_on_wins_over_ingestion_date(session, doc):
    row = session.get(StubDocument, 1)
    row.published_on = datetime.datetime(2026, 5, 1)
    row.ingested_at = datetime.datetime(2026, 10, 27)
    assert detect._reference_date(row) == datetime.date(2026, 5, 1)


def test_detect_merges_same_relation_from_one_article_into_one_proposal(session, doc, monkeypatch):
    relation = {"from": "brazylia", "to": "stany-zjednoczone", "axis": "political", "score": -1, "confidence": 1}
    _fake_llm(
        monkeypatch,
        [
            _candidate(relation=relation),
            _candidate(title="Drugie", quote="po wyborach w Brazylii", relation=relation),
        ],
    )
    out = detect.detect_for_document(session, 1)
    session.commit()
    assert out["events_created"] == 2 and out["assessments_proposed"] == 1 and out["assessments_merged"] == 1
    row = session.query(CountryRelationAssessment).one()
    assert len(row.evidence) == 2 and float(row.confidence) == svc.SINGLE_EVENT_CONFIDENCE_CAP


def test_detect_second_run_does_not_duplicate(session, doc, monkeypatch):
    relation = {"from": "brazylia", "to": "stany-zjednoczone", "axis": "political", "score": -1}
    _fake_llm(monkeypatch, [_candidate(relation=relation)])
    detect.detect_for_document(session, 1)
    session.commit()
    again = detect.detect_for_document(session, 1)
    session.commit()
    assert again["events_created"] == 0 and again["events_existing"] == 1 and again["assessments_proposed"] == 0
    assert session.query(GeoEvent).count() == 1
    assert session.query(CountryRelationAssessment).count() == 1


def test_detect_survives_garbage_and_skips_llm_without_countries(session, doc, monkeypatch):
    _fake_llm(monkeypatch, "przepraszam, nie umiem")
    assert detect.detect_for_document(session, 1)["candidates"] == 0
    monkeypatch.setattr(detect, "detect_countries", lambda text: [])
    calls = _fake_llm(monkeypatch, [_candidate()])
    assert detect.detect_for_document(session, 1)["fragments"] == 0 and calls == []


def test_detect_uses_the_default_model_and_reports_cost(session, doc, monkeypatch):
    from decimal import Decimal

    usage = SimpleNamespace(
        usage_log_id=7,
        total_tokens=1234,
        cost=SimpleNamespace(total_cost=Decimal("0.0042"), currency="USD", status="estimated"),
    )

    def fake(prompt, **kwargs):
        return SimpleNamespace(response_text="[]", usage=usage)

    monkeypatch.setattr(detect, "ai_ask", fake)
    out = detect.detect_for_document(session, 1)
    assert out["model"] == "default-model"
    assert out["usage"]["llm_cost_amount"] == "0.0042" and out["usage"]["llm_cost_currency"] == "USD"
    assert out["usage"]["llm_tokens"] == 1234 and out["usage"]["llm_calls"] == 1


def test_detect_unknown_or_empty_document(session, doc):
    with pytest.raises(svc.GeopoliticsError) as exc:
        detect.detect_for_document(session, 404)
    assert exc.value.status == 404
    session.get(StubDocument, 1).text_md = " "
    with pytest.raises(svc.GeopoliticsError):
        detect.detect_for_document(session, 1)


def test_parse_response_tolerates_fences_and_prose():
    assert detect.parse_response('```json\n[{"a": 1}]\n```') == [{"a": 1}]
    assert detect.parse_response("brak") == [] and detect.parse_response('{"a": 1}') == []


def test_split_fragments_caps_cost():
    text = "\n\n".join("akapit " * 50 for _ in range(500))
    fragments = detect.split_fragments(text, size=1000, limit=3)
    assert len(fragments) == 3 and all(len(f) <= 1000 for f in fragments)


def test_row_locks_are_limited_to_the_assessment_table():
    """`FOR UPDATE` on a query with joined-eager relationships fails on PostgreSQL ("nullable side of an outer
    join"), which SQLite does not notice; every lock must name its table (found out on the NAS)."""
    import inspect
    import re

    source = inspect.getsource(svc)
    locks = re.findall(r"with_for_update\(([^)]*)\)", source)
    assert locks and all("of=" in lock for lock in locks)


def test_detect_renders_the_active_template_and_records_its_version(session, doc, monkeypatch):
    from library.prompt_templates import ResolvedTemplate

    custom = ResolvedTemplate(
        5, "event_extraction-v3", None, "ZMIENIONY PROMPT: {{ countries }} | {{ reference_date }} | {{ fragment }}"
    )
    monkeypatch.setattr(detect.prompt_templates, "get_active", lambda s, task, variant: custom)
    relation = {"from": "brazylia", "to": "stany-zjednoczone", "axis": "political", "score": -1}
    calls = _fake_llm(monkeypatch, [_candidate(relation=relation)])
    out = detect.detect_for_document(session, 1)
    session.commit()
    assert calls[0][0].startswith("ZMIENIONY PROMPT: brazylia, stany-zjednoczone | nieznana |")
    assert "system_prompt" not in calls[0][1]
    assert out["prompt_version"] == "event_extraction-v3"
    assert session.query(GeoEvent).one().prompt_version == "event_extraction-v3"
    assert session.query(CountryRelationAssessment).one().prompt_version == "event_extraction-v3"


def test_detect_without_a_saved_version_uses_the_builtin_and_says_so(session, doc, monkeypatch):
    _fake_llm(monkeypatch, [_candidate()])
    out = detect.detect_for_document(session, 1)
    session.commit()
    assert out["prompt_version"] == "event_extraction-builtin"
    assert session.query(GeoEvent).one().prompt_version == "event_extraction-builtin"


def test_detect_sends_a_system_prompt_only_when_the_template_has_one(session, doc, monkeypatch):
    from library.prompt_templates import ResolvedTemplate

    custom = ResolvedTemplate(6, "event_extraction-v4", "Jesteś ostrożny. Osie: {{ axes }}", "{{ fragment }}")
    monkeypatch.setattr(detect.prompt_templates, "get_active", lambda s, task, variant: custom)
    calls = _fake_llm(monkeypatch, [])
    detect.detect_for_document(session, 1)
    assert calls[0][1]["system_prompt"].startswith("Jesteś ostrożny. Osie: political (Polityczna)")


def test_detect_reports_a_template_that_cannot_render(session, doc, monkeypatch):
    from library.prompt_templates import ResolvedTemplate

    broken = ResolvedTemplate(7, "event_extraction-v9", None, "{{ nieznana }}")
    monkeypatch.setattr(detect.prompt_templates, "get_active", lambda s, task, variant: broken)
    _fake_llm(monkeypatch, [])
    with pytest.raises(svc.GeopoliticsError) as exc:
        detect.detect_for_document(session, 1)
    assert "event_extraction-v9" in exc.value.message


TRANSCRIPT = "## Wstęp\nBrazylia wybrała prezydenta, a jego rywal uciekł do USA po wyborach.\n\n## Sponsor\nKup VPN i oszczędzaj w Rosji i Chinach, kod rabatowy GEO."


def test_detect_skips_advertisement_chapters_of_a_transcript(session, doc, monkeypatch):
    row = session.get(StubDocument, 1)
    row.text_md, row.text, row.chapter_types = None, TRANSCRIPT, ["TEMAT", "REKLAMA"]
    session.commit()
    ad_candidate = _candidate(title="Reklama VPN", quote="Kup VPN i oszczędzaj w Rosji i Chinach")
    calls = _fake_llm(
        monkeypatch, [_candidate(quote="Brazylia wybrała prezydenta, a jego rywal uciekł do USA"), ad_candidate]
    )
    out = detect.detect_for_document(session, 1)
    assert "Kup VPN" not in calls[0][0] and "Brazylia wybrała prezydenta" in calls[0][0]
    assert out["events_created"] == 1 and out["rejected"]["quote_not_found"] == 1


def test_detect_refuses_a_document_that_is_only_advertisement_and_noise(session, doc):
    row = session.get(StubDocument, 1)
    row.text_md, row.text, row.chapter_types = None, "## Sponsor\nKup VPN.\n\n## Szum\nsubskrybuj", ["REKLAMA", "SZUM"]
    session.commit()
    with pytest.raises(svc.GeopoliticsError) as exc:
        detect.detect_for_document(session, 1)
    assert "no text content" in exc.value.message


def test_countries_are_found_after_the_channel_glossary_but_the_prompt_keeps_the_original_text(
    session, doc, monkeypatch
):
    from library.country_gazetteer import detect_countries as real_detect

    monkeypatch.setattr(detect, "detect_countries", real_detect)
    monkeypatch.setattr(
        "library.entity_service.apply_channel_glossary_text",
        lambda session, document_id, text: text.replace("państwo z gwiazdką", "Izrael"),
    )
    session.get(StubDocument, 1).text_md = "Premier powiedział, że państwo z gwiazdką odpowie na atak w Libanie."
    session.commit()
    calls = _fake_llm(monkeypatch, [])
    detect.detect_for_document(session, 1)
    prompt = calls[0][0]
    assert "izrael" in prompt.split("slug z listy:")[1].split("\n")[0]
    assert "państwo z gwiazdką" in prompt  # the model reads the original wording
