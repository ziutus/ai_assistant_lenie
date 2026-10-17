"""Chapter boundary routes with mocked ORM sessions."""
from unittest.mock import MagicMock

import pytest

pytest.importorskip("sqlalchemy")
flask = pytest.importorskip("flask")

from library import chunk_review_routes as cr, document_editing  # noqa: E402
from library.db.models import Document  # noqa: E402
from library.transcript_chapter_boundaries import describe_sections, merge_chapter, move_boundary, split_chapter  # noqa: E402

TEXT = "## Pierwszy\n\nPierwsze. Drugie.\n\n## Drugi\n\nTrzecie. Czwarte."


@pytest.fixture
def setup(monkeypatch):
    doc = MagicMock(spec=Document)
    doc.text, doc.text_md, doc.text_raw, doc.chapter_list = TEXT, "markdown", "raw", "timestamps"
    session = MagicMock()
    session.get.return_value = doc
    session.scalar.side_effect = [None, 2]
    monkeypatch.setattr(cr, "get_scoped_session", lambda: session)
    embeddings = MagicMock(return_value=False)
    monkeypatch.setattr(document_editing, "document_has_embeddings", embeddings)
    app = flask.Flask(__name__)
    app.register_blueprint(cr.bp)
    app.testing = True
    return app.test_client(), session, doc, embeddings


def test_get(setup):
    client, session, doc, embeddings = setup
    session.scalar.side_effect = [2]
    response = client.get("/document/42/chapter_sections")
    assert response.status_code == 200
    assert response.json == {"status": "success", "doc_id": 42, "sections": describe_sections(TEXT),
                             "has_embeddings": False, "has_analysis_runs": True}
    embeddings.assert_called_once_with(session, 42)
    session.commit.assert_not_called()
    query = str(session.scalar.call_args.args[0])
    assert "document_analysis_runs.status !=" in query


@pytest.mark.parametrize("steps", [-1, 1])
def test_post_changes_only_text(setup, steps):
    client, session, doc, _ = setup
    response = client.post("/document/42/move_chapter_boundary", json={"position": 2, "sentences": steps})
    assert response.status_code == 200
    assert doc.text == move_boundary(TEXT, 2, steps)
    assert (doc.text_md, doc.text_raw, doc.chapter_list) == ("markdown", "raw", "timestamps")
    assert response.json["sections"] == describe_sections(doc.text)
    assert response.json["stale_analysis_runs"] == 2
    session.commit.assert_called_once()


@pytest.mark.parametrize("method,path", [("get", "chapter_sections"), ("post", "move_chapter_boundary"),
                                        ("post", "split_chapter"), ("post", "merge_chapter"),
                                        ("get", "chapter_sections/1/sentences")])
def test_not_found(setup, method, path):
    client, session, _, _ = setup
    session.get.return_value = None
    assert getattr(client, method)(f"/document/42/{path}").status_code == 404
    session.commit.assert_not_called()


@pytest.mark.parametrize("method,path", [("get", "chapter_sections"), ("post", "move_chapter_boundary"),
                                        ("post", "split_chapter"), ("post", "merge_chapter"),
                                        ("get", "chapter_sections/1/sentences")])
@pytest.mark.parametrize("text", [None, "", "  \n"])
def test_no_text(setup, method, path, text):
    client, session, doc, _ = setup
    doc.text = text
    assert getattr(client, method)(f"/document/42/{path}").status_code == 400
    session.commit.assert_not_called()


@pytest.mark.parametrize("operation", ["move_chapter_boundary", "split_chapter", "merge_chapter"])
def test_embeddings_conflict(setup, operation):
    client, session, doc, embeddings = setup
    embeddings.return_value = True
    response = client.post(f"/document/42/{operation}", json={"position": 2, "sentences": 1})
    assert response.status_code == 409
    assert "embeddings" in response.json["message"]
    assert doc.text == TEXT
    session.commit.assert_not_called()


@pytest.mark.parametrize("operation", ["move_chapter_boundary", "split_chapter", "merge_chapter"])
def test_active_job_conflict(setup, operation):
    client, session, doc, _ = setup
    session.scalar.side_effect = ["active-job"]
    response = client.post(f"/document/42/{operation}", json={"position": 2, "sentences": 1})
    assert response.status_code == 409
    assert "running" in response.json["message"]
    statement = session.scalar.call_args.args[0]
    assert ["queued", "running"] in statement.compile().params.values()
    assert doc.text == TEXT
    session.commit.assert_not_called()


@pytest.mark.parametrize("payload", [{"position": 1, "sentences": 1}, {"position": 2, "sentences": 0},
                                     {"position": 2, "sentences": 2}, {"position": 2, "sentences": -2},
                                     {"position": True, "sentences": 1}, {"position": 2, "sentences": False},
                                     {"position": "2", "sentences": 1}, {"position": 2, "sentences": 1.0},
                                     {}, [], None])
def test_invalid_input(setup, payload):
    client, session, doc, _ = setup
    response = client.post("/document/42/move_chapter_boundary", json=payload)
    assert response.status_code == 400
    assert response.json["message"]
    assert doc.text == TEXT
    session.commit.assert_not_called()


def test_value_error_message(setup):
    client, _, _, _ = setup
    with pytest.raises(ValueError) as error:
        move_boundary(TEXT, 1, 1)
    response = client.post("/document/42/move_chapter_boundary", json={"position": 1, "sentences": 1})
    assert response.json["message"] == str(error.value)


@pytest.mark.parametrize("operation,payload,expected", [
    ("split_chapter", {"position": 1, "sentence_index": 2, "title": "Nowy"}, split_chapter(TEXT, 1, 2, "Nowy")),
    ("merge_chapter", {"position": 2}, merge_chapter(TEXT, 2)),
])
def test_split_merge_success(setup, operation, payload, expected):
    client, session, doc, _ = setup
    response = client.post(f"/document/42/{operation}", json=payload)
    assert response.status_code == 200
    assert response.json == {"status": "success", "doc_id": 42, "sections": describe_sections(expected),
                             "has_embeddings": False, "has_analysis_runs": True, "stale_analysis_runs": 2}
    assert doc.text == expected
    assert (doc.text_md, doc.text_raw, doc.chapter_list) == ("markdown", "raw", "timestamps")
    session.commit.assert_called_once()


@pytest.mark.parametrize("operation,payload", [
    ("split_chapter", {"position": 1, "sentence_index": 1, "title": "Nowy"}),
    ("split_chapter", {"position": 1, "sentence_index": 2, "title": "# Nowy"}),
    ("split_chapter", {"position": 1, "sentence_index": 2, "title": ""}),
    ("split_chapter", {"position": 1, "sentence_index": True, "title": "Nowy"}),
    ("split_chapter", {"position": False, "sentence_index": 2, "title": "Nowy"}),
    ("split_chapter", {"position": 1, "sentence_index": 2.0, "title": "Nowy"}),
    ("split_chapter", {"position": 1, "sentence_index": 2, "title": 123}),
    ("split_chapter", {"position": 1, "sentence_index": 2}),
    ("merge_chapter", {"position": 1}), ("merge_chapter", {"position": 3}),
    ("merge_chapter", {"position": True}), ("merge_chapter", {"position": "2"}),
    ("merge_chapter", {"position": 2.0}),
])
def test_new_edit_invalid_input(setup, operation, payload):
    client, session, doc, _ = setup
    response = client.post(f"/document/42/{operation}", json=payload)
    assert response.status_code == 400
    assert response.json["message"]
    assert doc.text == TEXT
    session.commit.assert_not_called()


@pytest.mark.parametrize("operation", ["split_chapter", "merge_chapter"])
@pytest.mark.parametrize("payload", [None, [], {}, "invalid", True])
def test_new_edit_invalid_body(setup, operation, payload):
    client, session, doc, _ = setup
    assert client.post(f"/document/42/{operation}", json=payload).status_code == 400
    session.commit.assert_not_called()
    assert doc.text == TEXT


@pytest.mark.parametrize("position,expected", [(0, ["Wstęp."]), (1, ["Pierwsze.", "Drugie."]),
                                              (2, ["Trzecie.", "Czwarte."])])
def test_lazy_sentences(setup, position, expected):
    client, session, doc, _ = setup
    doc.text = "Wstęp.\n\n" + TEXT
    response = client.get(f"/document/42/chapter_sections/{position}/sentences")
    assert response.status_code == 200
    assert response.json == {"status": "success", "position": position,
                             "title": ["", "Pierwszy", "Drugi"][position],
                             "sentences": [{"index": i, "text": text} for i, text in enumerate(expected, 1)]}
    session.scalar.assert_not_called()
    session.commit.assert_not_called()


@pytest.mark.parametrize("position", [0, 3, 100])
def test_lazy_sentences_unknown_position(setup, position):
    client, session, _, _ = setup
    assert client.get(f"/document/42/chapter_sections/{position}/sentences").status_code == 400
    session.commit.assert_not_called()


@pytest.mark.parametrize("query,include", [("", False), ("?with_sentences=0", False), ("?with_sentences=1", True)])
def test_sections_optional_sentences(setup, query, include):
    from library.transcript_chapter_boundaries import chapter_sentences

    client, session, doc, _ = setup
    doc.text = "Przedmowa.\n\n" + TEXT
    session.scalar.side_effect = [2]
    response = client.get("/document/42/chapter_sections" + query)
    assert response.status_code == 200
    for section in response.json["sections"]:
        assert ("sentences" in section) is include
        if include:
            assert section["sentences"] == chapter_sentences(doc.text, section["position"])["sentences"]
            assert len(section["sentences"]) == section["sentence_count"]
    assert response.json["has_analysis_runs"] is True
    session.commit.assert_not_called()
