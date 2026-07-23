import datetime
import json
from types import SimpleNamespace
from unittest.mock import MagicMock

import flask
import pytest
from sqlalchemy import Date, Integer, String, Text, inspect

from imports import extract_events
from library import chunk_review_routes, timeline_events
from library.db.models import DocumentEvent


def fake_usage(usage_log_id=1, total_tokens=1):
    """Duck-typed UsageRecord for tests that stub ai_ask() directly."""
    return SimpleNamespace(
        usage_log_id=usage_log_id,
        total_tokens=total_tokens,
        cost=SimpleNamespace(total_cost=None, currency=None, status=SimpleNamespace(value="unknown")),
    )


def test_truncated_response_recovers_complete_objects():
    raw = '[{"date_text": "2020", "description": "Pierwsze", "quote": "Cytat"}, {"date_text": "2021"'

    assert timeline_events.parse_events_response(raw) == [
        {"date_text": "2020", "description": "Pierwsze", "quote": "Cytat"}
    ]


def test_truncated_response_without_complete_object_returns_empty_list():
    assert timeline_events.parse_events_response('[{"date_text": "2020"') == []


def test_valid_json_response_is_parsed_without_changes():
    payload = [{"date_text": "2020", "description": "Wydarzenie", "quote": "Cytat"}]

    assert timeline_events.parse_events_response(json.dumps(payload)) == payload


def test_timeline_prompt_includes_ner_hints_without_treating_them_as_events():
    prompt = timeline_events._timeline_prompt(
        "Spotkanie odbyło się 17 września 1939.",
        [{"entity_type": "date", "raw_text": "17 września 1939"}],
    )

    assert 'date: "17 września 1939"' in prompt
    assert "wyłącznie jako wskazówki" in prompt


def test_invalid_json_is_counted_in_fragment_report(monkeypatch):
    fragment = "W 2020 wydarzyło się pierwsze wydarzenie."
    raw = json.dumps([{
        "date_text": "2020",
        "description": "Pierwsze wydarzenie.",
        "quote": "W 2020 wydarzyło się pierwsze wydarzenie.",
    }])[:-1] + ', {"date_text": "2021"'
    monkeypatch.setattr(
        timeline_events,
        "ai_ask",
        lambda *_args, **_kwargs: SimpleNamespace(response_text=raw, usage=fake_usage()),
    )

    events, report = timeline_events.extract_fragment_events(fragment, 1, "model")

    assert len(events) == 1
    assert report["invalid_json"] == 1


def test_invalid_json_is_summed_in_chapter_report(monkeypatch):
    reports = iter([
        {
            "rejected_without_quote": 0,
            "rejected_without_date": 0,
            "invalid_json": 1,
            "llm_calls": 1,
            "usage_log_ids": [1],
            "llm_tokens": 10,
            "llm_cost_amount": None,
            "llm_cost_currency": None,
            "llm_cost_status": "unknown",
        },
        {
            "rejected_without_quote": 0,
            "rejected_without_date": 0,
            "invalid_json": 0,
            "llm_calls": 1,
            "usage_log_ids": [2],
            "llm_tokens": 10,
            "llm_cost_amount": None,
            "llm_cost_currency": None,
            "llm_cost_status": "unknown",
        },
    ])
    monkeypatch.setattr(
        timeline_events,
        "_chapters_for_document",
        lambda *_args, **_kwargs: [{"position": 47, "title": "Rozdział", "text": "tekst"}],
    )
    monkeypatch.setattr(timeline_events, "split_timeline_fragments", lambda _text: ["jeden", "dwa"])
    monkeypatch.setattr(
        timeline_events,
        "extract_fragment_events",
        lambda *_args, **_kwargs: ([], next(reports)),
    )

    result = timeline_events.extract_document_events(None, SimpleNamespace(), model="model")

    assert result["chapters"][0]["invalid_json"] == 1
    assert result["chapters"][0]["usage_log_ids"] == [1, 2]
    assert result["chapters"][0]["llm_tokens"] == 20


@pytest.mark.parametrize(
    "wrapper",
    [lambda payload: payload, lambda payload: f"```json\n{payload}\n```"],
)
def test_llm_response_parsing_with_optional_markdown_fence(monkeypatch, wrapper):
    fragment = "17 września 1939 Niemcy zaatakowały Polskę."
    payload = json.dumps([
        {
            "date_text": "17 września 1939",
            "description": "Niemcy zaatakowały Polskę.",
            "quote": "Niemcy zaatakowały Polskę.",
        }
    ], ensure_ascii=False)
    monkeypatch.setattr(
        timeline_events,
        "ai_ask",
        lambda *_args, **_kwargs: SimpleNamespace(response_text=wrapper(payload), usage=fake_usage(total_tokens=42)),
    )

    events, report = timeline_events.extract_fragment_events(fragment, 3, "test-model")

    assert len(events) == 1
    assert events[0]["chapter_position"] == 3
    assert events[0]["event_date"] == datetime.date(1939, 9, 17)
    assert report["llm_calls"] == 1
    assert report["llm_tokens"] == 42


def test_quote_outside_fragment_is_rejected(monkeypatch):
    payload = json.dumps([
        {
            "date_text": "1997",
            "description": "Opis wydarzenia.",
            "quote": "Tego cytatu nie ma w tekście.",
        }
    ])
    monkeypatch.setattr(
        timeline_events,
        "ai_ask",
        lambda *_args, **_kwargs: SimpleNamespace(response_text=payload, usage=fake_usage()),
    )

    events, report = timeline_events.extract_fragment_events("W 1997 wydarzyło się coś innego.", 1, "model")

    assert events == []
    assert report["rejected_without_quote"] == 1
    assert report["rejected_without_date"] == 0


@pytest.mark.parametrize(
    ("date_text", "precision", "event_date", "sort_year"),
    [
        ("17 września 1939", "day", datetime.date(1939, 9, 17), 1939),
        ("w marcu 1939 r.", "month", datetime.date(1939, 3, 1), 1939),
        ("1997", "year", datetime.date(1997, 1, 1), 1997),
        ("1914 rok", "year", datetime.date(1914, 1, 1), 1914),
        ("966", "year", datetime.date(966, 1, 1), 966),
        ("lata 90.", "decade", datetime.date(1990, 1, 1), 1990),
        ("XIX wieku", "century", datetime.date(1801, 1, 1), 1850),
        ("1918-1939", "year", datetime.date(1918, 1, 1), 1918),
        ("w latach 1918–1939", "year", datetime.date(1918, 1, 1), 1918),
        ("lata 1988 — 1998", "year", datetime.date(1988, 1, 1), 1988),
        ("luty 2024 r.", "month", datetime.date(2024, 2, 1), 2024),
        ("styczeń 2024 r.", "month", datetime.date(2024, 1, 1), 2024),
        ("sierpień 2023 r.", "month", datetime.date(2023, 8, 1), 2023),
    ],
)
def test_polish_date_normalization(date_text, precision, event_date, sort_year):
    result = timeline_events.normalize_date_text(date_text)

    assert result is not None
    assert result["date_precision"] == precision
    assert result["event_date"] == event_date
    assert result["sort_year"] == sort_year


def test_year_range_has_end_of_last_year():
    result = timeline_events.normalize_date_text("1918-1939")

    assert result is not None
    assert result["event_date_end"] == datetime.date(1939, 12, 31)


def test_compact_day_month_uses_publication_year():
    result = timeline_events.normalize_date_text("09.04", datetime.date(2026, 4, 9))

    assert result is not None
    assert result["event_date"] == datetime.date(2026, 4, 9)
    assert result["date_precision"] == "day"


def test_dateparser_result_with_unrelated_year_is_rejected(monkeypatch):
    monkeypatch.setattr(timeline_events.dateparser, "parse", lambda *_args, **_kwargs: datetime.datetime(112, 1, 1))

    assert timeline_events.normalize_date_text("około 1914 roku") is None


def test_grounded_quote_normalizes_typographic_dashes(monkeypatch):
    fragment = "W latach 1918–1939 państwo przechodziło liczne przemiany."
    payload = json.dumps([
        {
            "date_text": "1918-1939",
            "description": "Państwo przechodziło liczne przemiany.",
            "quote": "W latach 1918-1939 państwo przechodziło liczne przemiany.",
        }
    ], ensure_ascii=False)
    monkeypatch.setattr(
        timeline_events,
        "ai_ask",
        lambda *_args, **_kwargs: SimpleNamespace(response_text=payload, usage=fake_usage()),
    )

    events, report = timeline_events.extract_fragment_events(fragment, 1, "model")

    assert len(events) == 1
    assert report["rejected_without_quote"] == 0


@pytest.mark.parametrize(
    ("quote", "fragment"),
    [
        ('Autor powiedział "tak".', "Autor powiedział „tak”."),
        ("Historia d'Artagnana.", "Historia d’Artagnana."),
    ],
)
def test_grounded_quote_normalizes_typographic_quotes_and_apostrophes(quote, fragment):
    assert timeline_events._quote_is_grounded(quote, fragment)


def test_extract_events_configures_stdout_as_utf8(monkeypatch):
    stdout = MagicMock()
    monkeypatch.setattr(extract_events.sys, "stdout", stdout)

    extract_events._configure_stdout_utf8()

    stdout.reconfigure.assert_called_once_with(encoding="utf-8")


def test_refresh_uses_replace_semantics(monkeypatch):
    session = MagicMock()
    doc = SimpleNamespace(id=9204)
    extracted = {
        "model": "model",
        "chapters": [],
        "events": [
            {
                "chapter_position": 37,
                "date_text": "1997",
                "event_date": datetime.date(1997, 1, 1),
                "event_date_end": datetime.date(1997, 12, 31),
                "date_precision": "year",
                "sort_year": 1997,
                "description": "Wydarzenie.",
                "anchor_quote": "W 1997 wydarzenie.",
            }
        ],
    }
    monkeypatch.setattr(timeline_events, "extract_document_events", lambda *_args, **_kwargs: extracted)

    result = timeline_events.refresh_document_events(session, doc)

    session.execute.assert_called_once()
    delete_sql = str(session.execute.call_args.args[0])
    assert "DELETE FROM document_events" in delete_sql
    session.add_all.assert_called_once()
    row = session.add_all.call_args.args[0][0]
    assert row.document_id == 9204
    assert row.chapter_position == 37
    assert result["rows"] == [row]


def test_document_event_orm_model():
    mapper = inspect(DocumentEvent)
    columns = mapper.mapper.columns

    assert DocumentEvent.__tablename__ == "document_events"
    assert set(columns.keys()) == {
        "id",
        "document_id",
        "chapter_position",
        "event_date",
        "event_date_end",
        "date_precision",
        "date_text",
        "sort_year",
        "description",
        "anchor_quote",
        "created_at",
    }
    assert isinstance(columns["event_date"].type, Date)
    assert isinstance(columns["sort_year"].type, Integer)
    assert isinstance(columns["date_precision"].type, String)
    assert isinstance(columns["description"].type, Text)
    assert list(columns["document_id"].foreign_keys)[0].target_fullname == "documents.id"
    assert "idx_document_events_document_sort_year" in {index.name for index in DocumentEvent.__table__.indexes}


def test_document_events_endpoint(monkeypatch):
    row = DocumentEvent(
        document_id=7,
        chapter_position=2,
        date_text="1997",
        event_date=datetime.date(1997, 1, 1),
        event_date_end=datetime.date(1997, 12, 31),
        date_precision="year",
        sort_year=1997,
        description="Wydarzenie.",
        anchor_quote="W 1997 wydarzenie.",
    )
    query = MagicMock()
    query.filter.return_value.order_by.return_value.all.return_value = [row]
    session = MagicMock()
    session.get.return_value = SimpleNamespace(id=7)
    session.query.return_value = query
    monkeypatch.setattr(chunk_review_routes, "get_scoped_session", lambda: session)
    app = flask.Flask(__name__)
    app.register_blueprint(chunk_review_routes.bp)

    response = app.test_client().get("/document/7/events")

    assert response.status_code == 200
    assert response.get_json()["events"] == [
        {
            "date_text": "1997",
            "event_date": "1997-01-01",
            "event_date_end": "1997-12-31",
            "date_precision": "year",
            "sort_year": 1997,
            "description": "Wydarzenie.",
            "anchor_quote": "W 1997 wydarzenie.",
            "chapter_position": 2,
        }
    ]
