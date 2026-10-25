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
    doc.chapter_types = None
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
                                        ("post", "split_chapter"), ("post", "merge_chapter"), ("post", "chapter_type"),
                                        ("get", "chapter_sections/1/sentences"), ("get", "chapter_entities")])
def test_not_found(setup, method, path):
    client, session, _, _ = setup
    session.get.return_value = None
    assert getattr(client, method)(f"/document/42/{path}").status_code == 404
    session.commit.assert_not_called()


@pytest.mark.parametrize("method,path", [("get", "chapter_sections"), ("post", "move_chapter_boundary"),
                                        ("post", "split_chapter"), ("post", "merge_chapter"), ("post", "chapter_type"),
                                        ("get", "chapter_sections/1/sentences"), ("get", "chapter_entities")])
@pytest.mark.parametrize("text", [None, "", "  \n"])
def test_no_text(setup, method, path, text):
    client, session, doc, _ = setup
    doc.text = text
    assert getattr(client, method)(f"/document/42/{path}").status_code == 400
    session.commit.assert_not_called()


@pytest.mark.parametrize("operation", ["move_chapter_boundary", "split_chapter", "merge_chapter", "chapter_type"])
def test_embeddings_conflict(setup, operation):
    client, session, doc, embeddings = setup
    embeddings.return_value = True
    response = client.post(f"/document/42/{operation}", json={"position": 2, "sentences": 1})
    assert response.status_code == 409
    assert "embeddings" in response.json["message"]
    assert doc.text == TEXT
    session.commit.assert_not_called()


@pytest.mark.parametrize("operation", ["move_chapter_boundary", "split_chapter", "merge_chapter", "chapter_type"])
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


@pytest.mark.parametrize("operation", ["split_chapter", "merge_chapter", "chapter_type"])
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


@pytest.mark.parametrize("kind", ["TEMAT", "REKLAMA", "SZUM", "ZRODLA"])
def test_set_chapter_type_only(setup, kind):
    client, session, doc, _ = setup
    response = client.post("/document/42/chapter_type", json={"position": 2, "type": kind})
    assert response.status_code == 200
    assert doc.chapter_types == ["TEMAT", kind]
    assert doc.text == TEXT
    assert (doc.text_md, doc.text_raw, doc.chapter_list) == ("markdown", "raw", "timestamps")
    assert response.json["sections"][1]["type"] == kind
    assert response.json["stale_analysis_runs"] == 2
    session.commit.assert_called_once()


@pytest.mark.parametrize("payload", [
    {"position": 0, "type": "TEMAT"}, {"position": 3, "type": "TEMAT"},
    {"position": True, "type": "TEMAT"}, {"position": "1", "type": "TEMAT"},
    {"position": 1.0, "type": "TEMAT"}, {"position": 1, "type": "reklama"},
    {"position": 1, "type": "ŹRÓDŁA"}, {"position": 1, "type": []},
    {"position": 1}, {"type": "TEMAT"},
])
def test_invalid_chapter_type(setup, payload):
    client, session, doc, _ = setup
    assert client.post("/document/42/chapter_type", json=payload).status_code == 400
    assert doc.chapter_types is None
    assert doc.text == TEXT
    session.commit.assert_not_called()


@pytest.mark.parametrize("query", ["", "?with_sentences=1"])
def test_get_chapter_types(setup, query):
    client, session, doc, _ = setup
    doc.chapter_types = ["REKLAMA", "SZUM"]
    session.scalar.side_effect = [2]
    response = client.get("/document/42/chapter_sections" + query)
    assert [s["type"] for s in response.json["sections"]] == doc.chapter_types


def test_split_inherits_type_in_same_commit(setup):
    client, session, doc, _ = setup
    doc.chapter_types = ["REKLAMA", "TEMAT"]
    def check_commit():
        assert doc.text == split_chapter(TEXT, 1, 2, "Nowy")
        assert doc.chapter_types == ["REKLAMA", "REKLAMA", "TEMAT"]
    session.commit.side_effect = check_commit
    response = client.post("/document/42/split_chapter", json={"position": 1, "sentence_index": 2, "title": "Nowy"})
    assert response.status_code == 200
    session.commit.assert_called_once()


def test_merge_reports_type_conflict_in_same_commit(setup):
    client, session, doc, _ = setup
    doc.chapter_types = ["SZUM", "REKLAMA"]
    def check_commit():
        assert doc.text == merge_chapter(TEXT, 2)
        assert doc.chapter_types == ["SZUM"]
    session.commit.side_effect = check_commit
    response = client.post("/document/42/merge_chapter", json={"position": 2})
    assert response.status_code == 200
    assert response.json["type_conflict"] == {"kept": "SZUM", "dropped": "REKLAMA"}
    session.commit.assert_called_once()


def test_chunk_chapter_titles_prefer_explicit_h2_and_keep_legacy_timestamps():
    video = [{"title": "Oryginalny", "start_seconds": 0}]
    segments = [{"start": 0}, {"start": 10}]
    assert cr._chunk_chapters(0, 1, segments, video, [0], "## Własny\nTekst.") == ["Własny"]
    assert cr._chunk_chapters(None, None, [], [], [], "## Reklama\nTekst.") == ["Reklama"]
    assert cr._chunk_chapters(0, 1, segments, video, [0], "Tekst bez H2.") == ["Oryginalny"]


@pytest.mark.parametrize("preamble", ["", "Jan.\n\n"])
def test_chapter_entities_local_counts_and_positions(setup, monkeypatch, preamble):
    client, session, doc, embeddings = setup
    doc.text = preamble + "## Jan\n\nJan i Jan.\n\n## Reklama\n\nJan."
    doc.chapter_types = ["TEMAT", "REKLAMA"]
    grouped = {"persName": [{"text": "Jan", "count": 20, "variants": ["Jan"]}], "orgName": []}
    get_entities = MagicMock(return_value=grouped)
    monkeypatch.setattr("library.entity_service.get_document_entities", get_entities)
    response = client.get("/document/42/chapter_entities")
    assert response.status_code == 200
    assert response.json["has_entities"] is True
    sections = response.json["sections"]
    assert [s["position"] for s in sections] == ([0, 1, 2] if preamble else [1, 2])
    assert sections[-2]["entities"]["persName"][0]["count"] == 2
    assert sections[-1] == {"position": 2, "type": "REKLAMA", "entities": {"persName": [], "orgName": []},
                            "country_groups": []}
    assert sections[-2]["country_groups"] == []
    if preamble:
        assert sections[0]["entities"]["persName"][0]["count"] == 1
    assert grouped["persName"][0]["count"] == 20
    get_entities.assert_called_once_with(session, 42)
    embeddings.assert_not_called()
    session.commit.assert_not_called()


def test_chapter_entities_without_stored_entities(setup, monkeypatch):
    client, _, _, _ = setup
    monkeypatch.setattr("library.entity_service.get_document_entities", lambda *_: {"persName": []})
    assert client.get("/document/42/chapter_entities").json["has_entities"] is False


@pytest.mark.parametrize("position", [0, 1, 2])
def test_sections_selected_position(setup, position):
    client, session, doc, _ = setup
    doc.text = "Wstęp.\n\n" + TEXT
    session.scalar.side_effect = [2]
    response = client.get(f"/document/42/chapter_sections?position={position}&with_sentences=1")
    assert response.status_code == 200
    assert response.json["selected_position"] == position
    expected = describe_sections(doc.text, with_sentences=True)
    for actual, full in zip(response.json["sections"], expected, strict=True):
        if actual["position"] != position:
            full.pop("sentences")
        assert actual == full


@pytest.mark.parametrize("endpoint", ["chapter_sections", "chapter_entities"])
@pytest.mark.parametrize("position", ["", "abc", "1.5", "-1", "0", "3"])
def test_invalid_selected_position(setup, endpoint, position):
    client, _, _, _ = setup
    response = client.get(f"/document/42/{endpoint}?position={position}")
    assert response.status_code == 400
    assert response.json["message"]


@pytest.mark.parametrize("position", [0, 1, 2])
def test_entities_only_compute_selected_chapter(setup, monkeypatch, position):
    client, _, doc, _ = setup
    doc.text = "Jan.\n\n" + TEXT
    doc.chapter_types = ["TEMAT", "SZUM"]
    grouped = {"persName": [{"text": "Jan"}], "orgName": []}
    monkeypatch.setattr("library.entity_service.get_document_entities", lambda *_: grouped)
    filtered = MagicMock(return_value=grouped)
    countries = MagicMock(return_value=[{"name": "test"}])
    monkeypatch.setattr("library.entity_service.filter_entities_to_text", filtered)
    monkeypatch.setattr("library.country_group_gazetteer.detect_country_groups", countries)
    response = client.get(f"/document/42/chapter_entities?position={position}")
    assert response.status_code == 200
    assert response.json["has_entities"] is True
    assert [s["position"] for s in response.json["sections"]] == [0, 1, 2]
    for section in response.json["sections"]:
        selected = section["position"] == position and position != 2
        assert section["entities"] == (grouped if selected else {"persName": [], "orgName": []})
        assert section["country_groups"] == ([{"name": "test"}] if selected else [])
    assert filtered.call_count == countries.call_count == (0 if position == 2 else 1)
    if position != 2:
        from library.transcript_chapter_boundaries import parse_sections
        filtered.assert_called_once_with(grouped, parse_sections(doc.text)[position].body)
        countries.assert_called_once_with(parse_sections(doc.text)[position].body)
