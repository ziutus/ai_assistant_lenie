import json
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

pytest.importorskip("sqlalchemy")
pytest.importorskip("flask")

import flask  # noqa: E402
from sqlalchemy import Integer, String, Text, inspect  # noqa: E402

from library import chunk_review_routes, tones  # noqa: E402
from library.db.models import DocumentTone  # noqa: E402


def _candidate(**overrides) -> dict:
    candidate = {
        "emocja": "gniewny",
        "emocje_dodatkowe": [],
        "nacechowanie": "negatywne",
        "intensywnosc": "wysoka",
        "rejestry": ["obraźliwy"],
        "uzasadnienie": "Tekst zawiera liczne obelgi.",
    }
    candidate.update(overrides)
    return candidate


def test_valid_json_response_is_parsed():
    payload = _candidate()

    assert tones.parse_tone_response(json.dumps(payload, ensure_ascii=False)) == payload


def test_fenced_json_response_is_parsed():
    payload = _candidate()

    assert tones.parse_tone_response(f"```json\n{json.dumps(payload, ensure_ascii=False)}\n```") == payload


@pytest.mark.parametrize("raw", ["", "nie-json", '["lista"]', '{"emocja": "gniewny"'])
def test_unusable_response_returns_none(raw):
    assert tones.parse_tone_response(raw) is None


def test_normalize_returns_canonical_labels():
    result = tones.normalize_tone(_candidate())

    assert result == {
        "emotion": "gniewny",
        "secondary_emotions": None,
        "sentiment": "negatywne",
        "intensity": "wysoka",
        "registers": "obraźliwy",
        "evidence": "Tekst zawiera liczne obelgi.",
    }


def test_normalize_restores_diacritics_from_plain_ascii():
    result = tones.normalize_tone(_candidate(
        emocja="podniosly", intensywnosc="srednia", rejestry=["obrazliwy"],
    ))

    assert result["emotion"] == "podniosły"
    assert result["intensity"] == "średnia"
    assert result["registers"] == "obraźliwy"


def test_normalize_rejects_unknown_emotion():
    assert tones.normalize_tone(_candidate(emocja="entuzjastyczny")) is None


def test_normalize_drops_invalid_registers_and_duplicate_secondary():
    result = tones.normalize_tone(_candidate(
        emocje_dodatkowe=["gniewny", "smutny", "wymyślony"],
        rejestry=["wymyślony", "potoczny"],
    ))

    assert result["secondary_emotions"] == "smutny"
    assert result["registers"] == "potoczny"


def test_classify_fragment_reports_invalid_json(monkeypatch):
    monkeypatch.setattr(
        tones,
        "ai_ask",
        lambda *_args, **_kwargs: SimpleNamespace(response_text="nie-json", total_tokens=5),
    )

    tone, report = tones.classify_fragment("tekst", "model")

    assert tone is None
    assert report["invalid_json"] == 1
    assert report["rejected_invalid"] == 0


def test_classify_fragment_reports_rejected_candidate(monkeypatch):
    payload = json.dumps(_candidate(emocja="wymyślona"), ensure_ascii=False)
    monkeypatch.setattr(
        tones,
        "ai_ask",
        lambda *_args, **_kwargs: SimpleNamespace(response_text=payload, total_tokens=5),
    )

    tone, report = tones.classify_fragment("tekst", "model")

    assert tone is None
    assert report["invalid_json"] == 0
    assert report["rejected_invalid"] == 1


def test_extract_assigns_chapter_positions(monkeypatch):
    monkeypatch.setattr(
        tones,
        "_chapters_for_document",
        lambda *_args, **_kwargs: [
            {"position": 1, "title": "Rozdział 1", "text": "tekst pierwszy"},
            {"position": 2, "title": "Rozdział 2", "text": "tekst drugi"},
        ],
    )
    responses = iter([
        ({"emotion": "radosny", "secondary_emotions": None, "sentiment": "pozytywne",
          "intensity": "wysoka", "registers": None, "evidence": None}, {"invalid_json": 0}),
        (None, {"invalid_json": 1}),
    ])
    monkeypatch.setattr(tones, "classify_fragment", lambda *_args, **_kwargs: next(responses))

    result = tones.extract_document_tones(None, SimpleNamespace(), model="model")

    assert [(t["chapter_position"], t["emotion"]) for t in result["tones"]] == [(1, "radosny")]
    assert [report["tones"] for report in result["chapters"]] == [1, 0]


def test_refresh_uses_replace_semantics(monkeypatch):
    session = MagicMock()
    doc = SimpleNamespace(id=9204)
    extracted = {
        "model": "model",
        "chapters": [],
        "tones": [
            {
                "chapter_position": 9,
                "emotion": "neutralny",
                "secondary_emotions": None,
                "sentiment": "neutralne",
                "intensity": "niska",
                "registers": "formalny",
                "evidence": "Rzeczowy opis infrastruktury.",
            }
        ],
    }
    monkeypatch.setattr(tones, "extract_document_tones", lambda *_args, **_kwargs: extracted)

    result = tones.refresh_document_tones(session, doc)

    session.execute.assert_called_once()
    delete_sql = str(session.execute.call_args.args[0])
    assert "DELETE FROM document_tones" in delete_sql
    session.add_all.assert_called_once()
    row = session.add_all.call_args.args[0][0]
    assert row.document_id == 9204
    assert row.chapter_position == 9
    assert row.emotion == "neutralny"
    assert result["rows"] == [row]


def test_document_tone_orm_model():
    mapper = inspect(DocumentTone)
    columns = mapper.mapper.columns

    assert DocumentTone.__tablename__ == "document_tones"
    assert set(columns.keys()) == {
        "id",
        "document_id",
        "chapter_position",
        "emotion",
        "secondary_emotions",
        "sentiment",
        "intensity",
        "registers",
        "evidence",
        "created_at",
    }
    assert isinstance(columns["chapter_position"].type, Integer)
    assert isinstance(columns["emotion"].type, String)
    assert isinstance(columns["evidence"].type, Text)
    assert list(columns["document_id"].foreign_keys)[0].target_fullname == "web_documents.id"
    assert "idx_document_tones_document_chapter" in {
        index.name for index in DocumentTone.__table__.indexes
    }


def test_document_tones_endpoint(monkeypatch):
    row = DocumentTone(
        document_id=7,
        chapter_position=2,
        emotion="gniewny",
        secondary_emotions="smutny",
        sentiment="negatywne",
        intensity="wysoka",
        registers="obraźliwy",
        evidence="Liczne obelgi.",
    )
    query = MagicMock()
    query.filter.return_value.order_by.return_value.all.return_value = [row]
    session = MagicMock()
    session.get.return_value = SimpleNamespace(id=7)
    session.query.return_value = query
    monkeypatch.setattr(chunk_review_routes, "get_scoped_session", lambda: session)
    app = flask.Flask(__name__)
    app.register_blueprint(chunk_review_routes.bp)

    response = app.test_client().get("/document/7/tones")

    assert response.status_code == 200
    assert response.get_json()["tones"] == [
        {
            "chapter_position": 2,
            "emotion": "gniewny",
            "secondary_emotions": "smutny",
            "sentiment": "negatywne",
            "intensity": "wysoka",
            "registers": "obraźliwy",
            "evidence": "Liczne obelgi.",
        }
    ]
