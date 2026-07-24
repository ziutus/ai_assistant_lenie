import json
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

pytest.importorskip("sqlalchemy")
pytest.importorskip("flask")

import flask  # noqa: E402
from sqlalchemy import Boolean, Text, inspect  # noqa: E402

from library import chunk_review_routes  # noqa: E402
from library import control_question_selection as cqs  # noqa: E402
from library.db.models import ControlQuestion, DocumentControlAnswer  # noqa: E402


def fake_usage(usage_log_id=1, total_tokens=5):
    """Duck-typed UsageRecord for tests that stub ai_ask() directly."""
    return SimpleNamespace(
        usage_log_id=usage_log_id,
        total_tokens=total_tokens,
        cost=SimpleNamespace(total_cost=None, currency=None, status=SimpleNamespace(value="unknown")),
    )


def _question(id_=1, header="Jaką ma armię?", tags="wojsko"):
    return SimpleNamespace(id=id_, section_header=header, tags=tags)


class TestSelectFragment:
    def test_zero_candidates_makes_no_llm_call(self, monkeypatch):
        called = []
        monkeypatch.setattr(cqs, "ai_ask", lambda *a, **k: called.append(1))

        selections, report = cqs.select_fragment("tekst", [], "model")

        assert selections == []
        assert report == {"invalid_json": 0, "rejected_invalid": 0, "skipped_no_candidates": 1}
        assert called == []

    def test_valid_response_maps_index_to_question(self, monkeypatch):
        payload = json.dumps([{"index": 0, "answer_summary": "Ma silną armię.", "evidence": "cytat"}])
        monkeypatch.setattr(
            cqs, "ai_ask",
            lambda *a, **k: SimpleNamespace(response_text=payload, usage=fake_usage()),
        )

        selections, report = cqs.select_fragment("tekst", [_question()], "model")

        assert selections == [{
            "question_id": 1, "question_header": "Jaką ma armię?", "tags": "wojsko",
            "answer_summary": "Ma silną armię.", "evidence": "cytat",
        }]
        assert report["invalid_json"] == 0
        assert report["rejected_invalid"] == 0

    def test_fenced_json_is_parsed(self, monkeypatch):
        payload = json.dumps([{"index": 0, "answer_summary": "Odpowiedź."}])
        monkeypatch.setattr(
            cqs, "ai_ask",
            lambda *a, **k: SimpleNamespace(response_text=f"```json\n{payload}\n```", usage=fake_usage()),
        )

        selections, _ = cqs.select_fragment("tekst", [_question()], "model")

        assert selections[0]["answer_summary"] == "Odpowiedź."
        assert selections[0]["evidence"] is None

    def test_invalid_json_reports_and_selects_nothing(self, monkeypatch):
        monkeypatch.setattr(
            cqs, "ai_ask",
            lambda *a, **k: SimpleNamespace(response_text="nie-json", usage=fake_usage()),
        )

        selections, report = cqs.select_fragment("tekst", [_question()], "model")

        assert selections == []
        assert report["invalid_json"] == 1

    def test_out_of_range_index_is_rejected(self, monkeypatch):
        payload = json.dumps([{"index": 5, "answer_summary": "X"}])
        monkeypatch.setattr(
            cqs, "ai_ask",
            lambda *a, **k: SimpleNamespace(response_text=payload, usage=fake_usage()),
        )

        selections, report = cqs.select_fragment("tekst", [_question()], "model")

        assert selections == []
        assert report["rejected_invalid"] == 1

    def test_truncated_array_recovers_complete_objects(self, monkeypatch):
        # Response cut off mid-string (response token budget exceeded) — the second
        # object never closes. Mirrors library/timeline_events.py's recovery path.
        truncated = (
            '[{"index": 0, "answer_summary": "Ma silną armię."},'
            ' {"index": 1, "answer_summary": "odpowiedź uci'
        )
        monkeypatch.setattr(
            cqs, "ai_ask",
            lambda *a, **k: SimpleNamespace(response_text=truncated, usage=fake_usage()),
        )

        selections, report = cqs.select_fragment(
            "tekst", [_question(0, "Q0"), _question(1, "Q1")], "model",
        )

        assert [s["question_id"] for s in selections] == [0]
        assert report["invalid_json"] == 1

    def test_missing_answer_summary_is_rejected(self, monkeypatch):
        payload = json.dumps([{"index": 0, "answer_summary": ""}])
        monkeypatch.setattr(
            cqs, "ai_ask",
            lambda *a, **k: SimpleNamespace(response_text=payload, usage=fake_usage()),
        )

        selections, report = cqs.select_fragment("tekst", [_question()], "model")

        assert selections == []
        assert report["rejected_invalid"] == 1


class TestLoadCandidateQuestions:
    def test_empty_tags_returns_nothing_without_query(self):
        session = MagicMock()

        result = cqs.load_candidate_questions(session, [])

        assert result == []
        session.scalars.assert_not_called()

    def test_filters_by_tag_overlap(self):
        rows = [_question(1, tags="wojsko,sojusze"), _question(2, tags="gospodarka")]
        session = MagicMock()
        session.scalars.return_value.all.return_value = rows

        result = cqs.load_candidate_questions(session, ["gospodarka"])

        assert result == [rows[1]]


class TestExtractDocumentControlAnswers:
    def test_no_candidates_short_circuits_without_chapters(self, monkeypatch):
        monkeypatch.setattr(cqs, "load_candidate_questions", lambda *a, **k: [])
        chapters_called = []
        monkeypatch.setattr(cqs, "_chapters_for_document", lambda *a, **k: chapters_called.append(1))

        result = cqs.extract_document_control_answers(
            MagicMock(), SimpleNamespace(id=1, tags=""), model="model",
        )

        assert result == {"model": "model", "answers": [], "chapters": []}
        assert chapters_called == []

    def test_assigns_chapter_positions(self, monkeypatch):
        monkeypatch.setattr(cqs, "load_candidate_questions", lambda *a, **k: [_question()])
        monkeypatch.setattr(
            cqs, "_chapters_for_document",
            lambda *a, **k: [
                {"position": 1, "title": "Rozdział 1", "text": "tekst pierwszy"},
                {"position": 2, "title": "Rozdział 2", "text": "tekst drugi"},
            ],
        )
        responses = iter([
            ([{"question_id": 1, "question_header": "Q", "tags": "wojsko",
               "answer_summary": "A", "evidence": None}], {"invalid_json": 0}),
            ([], {"invalid_json": 0}),
        ])
        monkeypatch.setattr(cqs, "select_fragment", lambda *a, **k: next(responses))

        result = cqs.extract_document_control_answers(
            MagicMock(), SimpleNamespace(id=1, tags="wojsko"), model="model",
        )

        assert [(a["chapter_position"], a["answer_summary"]) for a in result["answers"]] == [(1, "A")]
        assert [report["answers"] for report in result["chapters"]] == [1, 0]


class TestRefreshDocumentControlAnswers:
    def test_replace_semantics(self, monkeypatch):
        session = MagicMock()
        doc = SimpleNamespace(id=9204, tags="wojsko")
        extracted = {
            "model": "model",
            "chapters": [],
            "answers": [{
                "chapter_position": 9, "question_id": 1, "question_header": "Q",
                "tags": "wojsko", "answer_summary": "A", "evidence": None,
            }],
        }
        monkeypatch.setattr(cqs, "extract_document_control_answers", lambda *a, **k: extracted)

        result = cqs.refresh_document_control_answers(session, doc)

        session.execute.assert_called_once()
        delete_sql = str(session.execute.call_args.args[0])
        assert "DELETE FROM document_control_answers" in delete_sql
        session.add_all.assert_called_once()
        row = session.add_all.call_args.args[0][0]
        assert row.document_id == 9204
        assert row.chapter_position == 9
        assert row.answer_summary == "A"
        assert result["rows"] == [row]


def test_control_question_orm_model():
    mapper = inspect(ControlQuestion)
    columns = mapper.mapper.columns

    assert ControlQuestion.__tablename__ == "control_questions"
    assert set(columns.keys()) == {
        "id", "source_file", "section_header", "body", "tags", "position", "active",
        "created_at", "updated_at",
    }
    assert isinstance(columns["active"].type, Boolean)
    assert isinstance(columns["section_header"].type, Text)


def test_document_control_answer_orm_model():
    mapper = inspect(DocumentControlAnswer)
    columns = mapper.mapper.columns

    assert DocumentControlAnswer.__tablename__ == "document_control_answers"
    assert set(columns.keys()) == {
        "id", "document_id", "chapter_position", "question_id", "question_header",
        "tags", "answer_summary", "evidence", "created_at",
    }
    assert list(columns["document_id"].foreign_keys)[0].target_fullname == "documents.id"
    assert list(columns["question_id"].foreign_keys)[0].target_fullname == "control_questions.id"
    assert "idx_document_control_answers_document_chapter" in {
        index.name for index in DocumentControlAnswer.__table__.indexes
    }


def test_document_control_questions_endpoint(monkeypatch):
    row = DocumentControlAnswer(
        document_id=7, chapter_position=2, question_id=3, question_header="Jaką ma armię?",
        tags="wojsko", answer_summary="Ma silną armię.", evidence="cytat",
    )
    query = MagicMock()
    query.filter.return_value.order_by.return_value.all.return_value = [row]
    session = MagicMock()
    session.get.return_value = SimpleNamespace(id=7)
    session.query.return_value = query
    monkeypatch.setattr(chunk_review_routes, "get_scoped_session", lambda: session)
    app = flask.Flask(__name__)
    app.register_blueprint(chunk_review_routes.bp)

    response = app.test_client().get("/document/7/control_questions")

    assert response.status_code == 200
    assert response.get_json()["control_questions"] == [{
        "chapter_position": 2, "question_id": 3, "question_header": "Jaką ma armię?",
        "tags": "wojsko", "answer_summary": "Ma silną armię.", "evidence": "cytat",
    }]
