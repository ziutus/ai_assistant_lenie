"""Offline coverage of persisted anchors, REST validation and step-7 routing."""

import copy
import hashlib
import json
from types import SimpleNamespace
from unittest.mock import MagicMock, Mock, patch

import pytest

from library import outline_boundaries as ob
from library import document_analysis_service as das
from library.chunk_llm_analysis import remove_speech_fillers
from library.db.models import Document, DocumentChunk
from library.document_service import DocumentService


OUTLINE = "### Opening\nIntroduction.\n### Second\nDetails."
TEXT = "Opening sentence. " + "Background details. " * 65 + "Second yyy topic begins. " + "More details. " * 85


def payload():
    return ob.build_anchor_payload(TEXT, OUTLINE, {"starts": [
        {"id": 0, "sentence": "Opening sentence."}, {"id": 1, "sentence": "Second yyy topic begins."},
    ]})


def test_outline_anchor_payload_hash_and_filler_offsets():
    data = payload()
    assert data["outline_sha256"] == hashlib.sha256(OUTLINE.encode("utf-8")).hexdigest()
    assert data["anchors"][1]["sentence"] == "Second yyy topic begins."
    cleaned = remove_speech_fillers(TEXT)
    assert ob.anchors_to_starts(cleaned, data["anchors"]) == [0, cleaned.index("Second topic")]
    assert Document(outline_anchors=data).dict()["outline_anchors"] == data
    assert Document.__table__.c.outline_anchors.nullable
    assert Document.__table__.c.outline_anchors.type.none_as_null


def test_outline_anchor_order_uniqueness_normalisation_and_first_retained(caplog):
    text = "Teaser. First. Second. Repeated. Repeated. Łódź jest piękna."
    sentences = [None, "Second.", "First.", "Repeated.", "Lodz jest piekna.", "Absent."]
    outline = "\n".join(f"### Topic {i}" for i in range(len(sentences)))
    quotes = {"starts": [{"id": i, "sentence": s} for i, s in enumerate(sentences)]}
    result = ob.build_anchor_payload(text, outline, quotes)
    assert [a["title"] for a in result["anchors"]] == ["Topic 1", "Topic 4"]
    assert ob.anchors_to_starts(text, result["anchors"]) == [0, text.index("Łódź")]
    assert caplog.text.count("Dropped outline topic") == 4
    assert ob.anchors_to_starts("", result["anchors"]) == [None, None]


@pytest.mark.parametrize("quotes", [[], {}, {"starts": None}, {"starts": [None]},
    {"starts": [{"id": True, "sentence": "Opening sentence."}]},
    {"starts": [{"id": 9, "sentence": "Opening sentence."}]},
    {"starts": [{"id": 0, "sentence": " "}]},
    {"starts": [{"id": 0, "sentence": "x" * 601}]},
    {"starts": [{"id": 0, "sentence": None}, {"id": 0, "sentence": None}]},
])
def test_outline_quotes_reject_malformed_input(quotes):
    with pytest.raises(ValueError):
        ob.build_anchor_payload(TEXT, OUTLINE, quotes)


def invalid_payloads():
    good = payload()
    return [[], {}, {**good, "version": True}, {**good, "version": 2},
            {**good, "outline_sha256": "wrong"}, {**good, "anchors": {}},
            {**good, "anchors": good["anchors"] * 21}, {**good, "extra": 1},
            *[{**good, "anchors": [anchor]} for anchor in [
                None, {}, {"title": "Topic", "sentence": None}, {"title": "", "sentence": "Text."},
                {"title": "Topic", "sentence": " "}, {"title": "Topic", "sentence": "x" * 601},
                {"title": "Topic\nInjected", "sentence": "Text."},
            ]]]


@pytest.mark.parametrize("data", invalid_payloads())
def test_outline_payload_validation(data):
    with pytest.raises(ValueError, match="outline_anchors"):
        ob.validate_anchor_payload(data)


@pytest.mark.parametrize("value", [None, "", payload()])
def test_outline_service_updates_only_supplied_anchors(value):
    session = MagicMock()
    doc = Document(id=42, url="https://example.com", document_type="youtube", text=TEXT,
                   outline_md=OUTLINE, outline_anchors=payload(), chapter_list="0:00 Real chapter")
    with patch.object(Document, "get_by_id", return_value=doc):
        DocumentService(session).save_document(url=doc.url, link_id=42, outline_anchors=value)
    assert doc.outline_anchors == (None if value == "" else value)
    assert doc.outline_md == OUTLINE and doc.text == TEXT and doc.chapter_list == "0:00 Real chapter"
    session.commit.assert_called_once()


def test_outline_service_omission_preserves_anchors_and_invalid_never_commits():
    session = MagicMock()
    doc = Document(id=42, url="https://example.com", document_type="youtube", outline_anchors=payload())
    with patch.object(Document, "get_by_id", return_value=doc):
        DocumentService(session).save_document(url=doc.url, link_id=42, title="Changed")
        assert doc.outline_anchors == payload()
        session.reset_mock()
        with pytest.raises(ValueError):
            DocumentService(session).save_document(url=doc.url, link_id=42, outline_anchors={})
        session.commit.assert_not_called()


@pytest.fixture(autouse=True)
def offline_config(monkeypatch):
    # Patch configuration before importing server, without consulting Vault.
    from library.config_loader import Config

    settings = {"SECRETS_BACKEND": "env", "ENV_DATA": "test", "LLM_PROVIDER": "test",
                "AI_MODEL_SUMMARY": "test", "BACKEND_TYPE": "postgresql", "POSTGRESQL_HOST": "localhost",
                "POSTGRESQL_DATABASE": "test", "POSTGRESQL_USER": "test", "POSTGRESQL_PASSWORD": "test",
                "POSTGRESQL_PORT": "5432", "EMBEDDING_MODEL": "test", "PORT": "5055"}
    for key, value in settings.items():
        monkeypatch.setenv(key, value)
    with patch("library.config_loader.load_config", return_value=Config(settings)):
        monkeypatch.setattr("library.ai.ai_ask", lambda *args, **kwargs: pytest.fail("Unexpected LLM call"))
        yield


@pytest.fixture
def anchor_client(offline_config):
    import server

    with patch.object(server, "check_auth_header"), patch.object(server, "get_scoped_session") as scoped:
        scoped.return_value = MagicMock()
        yield server.app.test_client(), scoped.return_value


@pytest.mark.parametrize("raw", ["not JSON", *[json.dumps(v) for v in invalid_payloads()]])
def test_website_save_outline_validation(anchor_client, raw):
    client, session = anchor_client
    with patch("server.DocumentService") as service:
        response = client.post("/website_save", data={"url": "https://example.com", "outline_anchors": raw})
    assert response.status_code == 400
    assert "outline_anchors" in response.json["message"]
    service.assert_not_called()
    session.commit.assert_not_called()


@pytest.mark.parametrize("raw,expected", [("", None), ("null", None), (json.dumps(payload()), payload())])
def test_website_save_outline_form_and_get(anchor_client, raw, expected):
    client, session = anchor_client
    session.get.return_value = None
    session.execute.return_value.scalar.return_value = None
    doc = Document(id=42, url="https://example.com", document_type="youtube", outline_anchors=expected)
    with patch("server.DocumentService") as service:
        service.return_value.save_document.return_value = doc
        response = client.post("/website_save", data={"id": "42", "url": doc.url, "outline_anchors": raw})
        assert response.status_code == 200
        assert service.return_value.save_document.call_args.kwargs == {
            "url": doc.url, "link_id": 42, "processing_status": None,
            "document_type": None, "outline_anchors": expected,
        }
        service.return_value.get_document.return_value = doc
        response = client.get("/website_get?id=42")
        assert response.status_code == 200
        assert response.json["outline_anchors"] == expected


def run_split(monkeypatch, **overrides):
    doc = SimpleNamespace(id=42, title="Video", document_type="youtube", text=TEXT, text_md=None,
                          text_raw=None, chapter_list=None, outline_md=OUTLINE, outline_anchors=payload())
    for key, value in overrides.items():
        setattr(doc, key, value)
    session = MagicMock()
    added = []
    session.add.side_effect = added.append
    monkeypatch.setattr(das.Document, "get_by_id", lambda *args: doc)
    speakers = [{"name": "One"}, {"name": "Two"}] if overrides.get("labeled") else []
    logs = []
    das.DocumentAnalysisService(session).create_run(
        42, "unused", split_only=True, speakers=speakers, progress_fn=logs.append, document_enriched=True,
    )
    return [item.original_text for item in added if isinstance(item, DocumentChunk)], logs


def test_analysis_outline_anchors_post_filler_chapter_path(monkeypatch):
    chunks, logs = run_split(monkeypatch)
    assert len(chunks) == 2
    assert chunks[0].startswith("## Opening\n\nOpening sentence.")
    assert chunks[1].startswith("## Second\n\nSecond topic begins.")
    assert any("outline-anchor split" in line for line in logs)


@pytest.mark.parametrize("case", ["stale", "invalid", "missing", "ambiguous", "one", "labeled", "not_youtube"])
def test_analysis_outline_fallback(monkeypatch, case):
    data = copy.deepcopy(payload())
    overrides = {"outline_anchors": data}
    if case == "stale":
        overrides["outline_md"] = OUTLINE + "\nChanged"
    elif case == "invalid":
        data["version"] = 9
    elif case == "missing":
        data["anchors"][1]["sentence"] = "Missing."
    elif case == "ambiguous":
        data["anchors"][1]["sentence"] = "More details."
    elif case == "one":
        data["anchors"] = data["anchors"][:1]
    elif case == "labeled":
        overrides.update(text=TEXT.replace("Second", ">> Second"), labeled=True)
    else:
        overrides["document_type"] = "movie"
    chunks, logs = run_split(monkeypatch, **overrides)
    assert all("## Opening" not in c and "## Second" not in c for c in chunks)
    if case == "stale":
        assert any("stale outline hash" in line for line in logs)


def test_analysis_outline_chapter_list_has_priority_even_when_unlocatable(monkeypatch):
    for text in ["## Real\n\n" + "First. " * 30 + "\n\n## Next\n\n" + "Second. " * 30, TEXT]:
        chunks, logs = run_split(monkeypatch, text=text, chapter_list="0:00 Real\n1:00 Next")
        assert not any("outline-anchor split" in line for line in logs)
        assert all("## Opening" not in c for c in chunks)


@pytest.mark.parametrize("result", [None, RuntimeError("split failed")])
def test_analysis_outline_split_failure_falls_back(monkeypatch, result):
    splitter = Mock(side_effect=result) if isinstance(result, Exception) else Mock(return_value=result)
    monkeypatch.setattr(das, "_chapter_chunks_from_text", splitter)
    chunks, _ = run_split(monkeypatch)
    from library.text_functions import split_text_into_sentence_chunks

    assert chunks == split_text_into_sentence_chunks(remove_speech_fillers(TEXT), 5000)


def test_outline_preview_quotes_never_calls_llm_and_emits_json(monkeypatch, tmp_path, capsys):
    from imports import outline_chunk_preview as preview

    monkeypatch.setenv("LENIE_API_KEY", "test-key")
    get = Mock(return_value=SimpleNamespace(status_code=200, raise_for_status=lambda: None, json=lambda: {
        "document_type": "youtube", "text": TEXT, "outline_md": OUTLINE + "\n### Missing",
    }))
    monkeypatch.setattr(preview.requests, "get", get)
    llm = Mock(side_effect=AssertionError("No LLM calls"))
    monkeypatch.setattr(preview, "_read_only_llm", llm)
    monkeypatch.setattr(preview, "locate_topic_starts", llm)
    quotes = tmp_path / "quotes.json"
    quotes.write_text(json.dumps({"starts": [{"id": i, "sentence": a["sentence"]}
                                           for i, a in enumerate(payload()["anchors"])]}), encoding="utf-8")
    assert preview.main(["42", "--quotes", str(quotes), "--emit-anchors"]) == 0
    output = capsys.readouterr()
    assert json.loads(output.out)["anchors"] == payload()["anchors"]
    assert "New (outline-based): 2 chunks" in output.err
    assert "START:" in output.err and "END:" in output.err and "Missing | start: DROPPED" in output.err
    llm.assert_not_called()
    get.assert_called_once()


def test_outline_migration_has_single_head():
    from alembic.script import ScriptDirectory

    scripts = ScriptDirectory("alembic")
    assert scripts.get_heads() == ["c83f0e2a619d"]
    assert scripts.get_revision("c83f0e2a619d").down_revision == "a84d921cf607"


def test_outline_payload_accepts_limit_values():
    data = payload()
    data["anchors"] = [{"title": "Topic", "sentence": "x" * 600}] * 40
    assert ob.validate_anchor_payload(data) == data
    assert ob.validate_anchor_payload({**data, "anchors": []})["anchors"] == []


@pytest.mark.parametrize("outline", ["", "No headings", "\n".join(f"### Topic {i}" for i in range(41))])
def test_outline_payload_requires_bounded_topic_list(outline):
    with pytest.raises(ValueError, match="between 1 and 40"):
        ob.build_anchor_payload(TEXT, outline, {"starts": []})


@pytest.mark.parametrize("quotes", [None, {"starts": [{"id": 0, "sentence": "Opening sentence."}]}])
def test_outline_preview_emit_llm_mode_or_one_topic_fallback(monkeypatch, tmp_path, capsys, quotes):
    from imports import outline_chunk_preview as preview

    monkeypatch.setenv("LENIE_API_KEY", "test-key")
    monkeypatch.setattr(preview.requests, "get", Mock(return_value=SimpleNamespace(
        status_code=200, raise_for_status=lambda: None,
        json=lambda: {"document_type": "youtube", "text": TEXT, "outline_md": OUTLINE},
    )))
    fake = Mock(return_value=json.dumps({"starts": [
        {"id": i, "sentence": a["sentence"]} for i, a in enumerate(payload()["anchors"])
    ]}))
    monkeypatch.setattr(preview, "_read_only_llm", fake)
    args = ["42", "--emit-anchors"]
    if quotes is not None:
        path = tmp_path / "quotes.json"
        path.write_text(json.dumps(quotes), encoding="utf-8")
        args += ["--quotes", str(path)]
    assert preview.main(args) == 0
    output = capsys.readouterr()
    if quotes is None:
        assert json.loads(output.out) == payload()
        fake.assert_called_once()
    else:
        assert len(json.loads(output.out)["anchors"]) == 1
        assert "production will use the size-based split" in output.err
        fake.assert_not_called()
