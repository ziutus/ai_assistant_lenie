import json
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

pytest.importorskip("sqlalchemy")
pytest.importorskip("flask")

import flask  # noqa: E402
from sqlalchemy import Integer, String, Text, inspect  # noqa: E402

from library import chunk_review_routes, time_periods  # noqa: E402
from library.db.models import DocumentTimePeriod  # noqa: E402


def fake_usage(usage_log_id=1, total_tokens=1):
    """Duck-typed UsageRecord for tests that stub ai_ask() directly."""
    return SimpleNamespace(
        usage_log_id=usage_log_id,
        total_tokens=total_tokens,
        cost=SimpleNamespace(total_cost=None, currency=None, status=SimpleNamespace(value="unknown")),
    )


def _period(**overrides) -> dict:
    period = {
        "period_label": "zimna wojna",
        "period_start_year": 1947,
        "period_end_year": 1991,
        "confidence": "high",
        "evidence": "Tekst opisuje kryzys kubański.",
    }
    period.update(overrides)
    return period


def test_valid_json_response_is_parsed_without_changes():
    payload = [_period()]

    assert time_periods.parse_periods_response(json.dumps(payload, ensure_ascii=False)) == payload


def test_fenced_json_response_is_parsed():
    payload = [_period()]

    assert time_periods.parse_periods_response(f"```json\n{json.dumps(payload, ensure_ascii=False)}\n```") == payload


def test_truncated_response_recovers_complete_objects():
    raw = '[{"period_label": "zimna wojna", "period_start_year": 1947}, {"period_label": "wspoł'

    assert time_periods.parse_periods_response(raw) == [
        {"period_label": "zimna wojna", "period_start_year": 1947}
    ]


def test_dict_response_with_periods_key_is_unwrapped():
    payload = {"periods": [_period()]}

    assert time_periods.parse_periods_response(json.dumps(payload, ensure_ascii=False)) == [_period()]


def test_normalize_keeps_negative_bce_years():
    result = time_periods.normalize_period(_period(
        period_label="starożytny Egipt", period_start_year=-1550, period_end_year=-1070,
    ))

    assert result["period_label"] == "starożytny Egipt"
    assert result["period_start_year"] == -1550
    assert result["period_end_year"] == -1070


def test_normalize_swaps_reversed_years():
    result = time_periods.normalize_period(_period(period_start_year=-1070, period_end_year=-1550))

    assert result["period_start_year"] == -1550
    assert result["period_end_year"] == -1070


def test_normalize_rejects_missing_label():
    assert time_periods.normalize_period(_period(period_label="  ")) is None


@pytest.mark.parametrize("year", ["około 1200", 99999, -20000, True, 12.5])
def test_normalize_drops_unusable_years(year):
    result = time_periods.normalize_period(_period(period_start_year=year))

    assert result["period_start_year"] is None


def test_normalize_defaults_unknown_confidence_to_low():
    result = time_periods.normalize_period(_period(confidence="pewne"))

    assert result["confidence"] == "low"


def test_classify_fragment_dedupes_labels_and_caps_count(monkeypatch):
    payload = json.dumps([
        _period(period_label="zimna wojna"),
        _period(period_label="Zimna Wojna"),
        _period(period_label="współczesność"),
        _period(period_label="PRL"),
        _period(period_label="lata 90."),
    ], ensure_ascii=False)
    monkeypatch.setattr(
        time_periods,
        "ai_ask",
        lambda *_args, **_kwargs: SimpleNamespace(response_text=payload, usage=fake_usage(total_tokens=42)),
    )

    periods, report = time_periods.classify_fragment("tekst", "test-model")

    assert [period["period_label"] for period in periods] == ["zimna wojna", "współczesność", "PRL"]
    assert report["llm_calls"] == 1
    assert report["llm_tokens"] == 42
    assert report["invalid_json"] == 0


def test_classify_fragment_counts_rejected_candidates(monkeypatch):
    payload = json.dumps([_period(), _period(period_label="")], ensure_ascii=False)
    monkeypatch.setattr(
        time_periods,
        "ai_ask",
        lambda *_args, **_kwargs: SimpleNamespace(response_text=payload, usage=fake_usage()),
    )

    periods, report = time_periods.classify_fragment("tekst", "model")

    assert len(periods) == 1
    assert report["rejected_invalid"] == 1


def test_extract_assigns_chapter_and_ordering_positions(monkeypatch):
    monkeypatch.setattr(
        time_periods,
        "_chapters_for_document",
        lambda *_args, **_kwargs: [
            {"position": 1, "title": "Rozdział 1", "text": "tekst pierwszy"},
            {"position": 2, "title": "Rozdział 2", "text": "tekst drugi"},
        ],
    )
    responses = iter([
        ([{"period_label": "zimna wojna"}, {"period_label": "współczesność"}], {"invalid_json": 0}),
        ([{"period_label": "średniowiecze"}], {"invalid_json": 0}),
    ])
    monkeypatch.setattr(time_periods, "classify_fragment", lambda *_args, **_kwargs: next(responses))

    result = time_periods.extract_document_periods(None, SimpleNamespace(), model="model")

    assert [(p["chapter_position"], p["position"], p["period_label"]) for p in result["periods"]] == [
        (1, 0, "zimna wojna"),
        (1, 1, "współczesność"),
        (2, 0, "średniowiecze"),
    ]
    assert [report["periods"] for report in result["chapters"]] == [2, 1]


def test_refresh_uses_replace_semantics(monkeypatch):
    session = MagicMock()
    doc = SimpleNamespace(id=9204)
    extracted = {
        "model": "model",
        "chapters": [],
        "periods": [
            {
                "chapter_position": 37,
                "position": 0,
                "period_label": "II wojna światowa",
                "period_start_year": 1939,
                "period_end_year": 1945,
                "confidence": "high",
                "evidence": "Opis kampanii wrześniowej.",
            }
        ],
    }
    monkeypatch.setattr(time_periods, "extract_document_periods", lambda *_args, **_kwargs: extracted)

    result = time_periods.refresh_document_periods(session, doc)

    session.execute.assert_called_once()
    delete_sql = str(session.execute.call_args.args[0])
    assert "DELETE FROM document_time_periods" in delete_sql
    session.add_all.assert_called_once()
    row = session.add_all.call_args.args[0][0]
    assert row.document_id == 9204
    assert row.chapter_position == 37
    assert row.period_label == "II wojna światowa"
    assert result["rows"] == [row]


def test_document_time_period_orm_model():
    mapper = inspect(DocumentTimePeriod)
    columns = mapper.mapper.columns

    assert DocumentTimePeriod.__tablename__ == "document_time_periods"
    assert set(columns.keys()) == {
        "id",
        "document_id",
        "chapter_position",
        "position",
        "period_label",
        "period_start_year",
        "period_end_year",
        "confidence",
        "evidence",
        "created_at",
    }
    assert isinstance(columns["period_start_year"].type, Integer)
    assert isinstance(columns["period_label"].type, String)
    assert isinstance(columns["evidence"].type, Text)
    assert list(columns["document_id"].foreign_keys)[0].target_fullname == "web_documents.id"
    assert "idx_document_time_periods_document_chapter" in {
        index.name for index in DocumentTimePeriod.__table__.indexes
    }


def test_document_time_periods_endpoint(monkeypatch):
    row = DocumentTimePeriod(
        document_id=7,
        chapter_position=2,
        position=0,
        period_label="zimna wojna",
        period_start_year=1947,
        period_end_year=1991,
        confidence="high",
        evidence="Kryzys kubański.",
    )
    query = MagicMock()
    query.filter.return_value.order_by.return_value.all.return_value = [row]
    session = MagicMock()
    session.get.return_value = SimpleNamespace(id=7)
    session.query.return_value = query
    monkeypatch.setattr(chunk_review_routes, "get_scoped_session", lambda: session)
    app = flask.Flask(__name__)
    app.register_blueprint(chunk_review_routes.bp)

    response = app.test_client().get("/document/7/time_periods")

    assert response.status_code == 200
    assert response.get_json()["time_periods"] == [
        {
            "chapter_position": 2,
            "position": 0,
            "period_label": "zimna wojna",
            "period_start_year": 1947,
            "period_end_year": 1991,
            "confidence": "high",
            "evidence": "Kryzys kubański.",
        }
    ]
