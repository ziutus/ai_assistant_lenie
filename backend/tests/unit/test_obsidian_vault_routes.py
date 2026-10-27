"""Unit tests for library/obsidian_vault_routes.py -- the service-key-only vault gateway (ADR-030 Etap A2)."""

import os
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

pytest.importorskip("sqlalchemy")
flask = pytest.importorskip("flask")

from library import obsidian_vault as ov  # noqa: E402
from library import obsidian_vault_routes as vr  # noqa: E402

NOTE = "02-wiedza/Informatyka/AI/AI Lokalnie/Nowa notatka.md"
BODY = "---\ntags:\n  - wiedza/informatyka\n---\n# Nowa\n"


@pytest.fixture
def vault(tmp_path, monkeypatch):
    root = tmp_path / "vault"
    (root / "02-wiedza" / "Informatyka").mkdir(parents=True)
    (root / "02-wiedza" / "_index.md").write_text("# Indeks\n", encoding="utf-8")
    (root / "02-wiedza" / "Informatyka" / "Stare LLM.md").write_text(
        "---\ntags:\n  - wiedza/ai\n---\n# Stare\n", encoding="utf-8")
    (root / "tajne.md").write_text("tajne", encoding="utf-8")
    real = os.path.realpath(root)
    monkeypatch.setattr(ov, "_vault_root", lambda: real)
    session = MagicMock()
    monkeypatch.setattr(vr, "get_scoped_session", lambda: session)
    return root


def make_client(kind="service"):
    app = flask.Flask(__name__)
    app.register_blueprint(vr.bp)

    @app.before_request
    def _auth():
        flask.g.auth = SimpleNamespace(kind=kind)

    return app.test_client()


def apply(client, files):
    return client.post("/vault/apply", json={"files": files})


def test_requires_service_key(vault):
    for kind in ("user", "read_only"):
        c = make_client(kind)
        assert c.get("/vault/note?path=02-wiedza/_index.md").status_code == 403
        assert c.get("/vault/find?q=llm").status_code == 403
        assert apply(c, [{"path": NOTE, "content": BODY}]).status_code == 403


def test_read_note_and_hash(vault):
    resp = make_client().get("/vault/note?path=02-wiedza/_index.md")
    data = resp.get_json()
    assert resp.status_code == 200 and data["text"] == "# Indeks\n"
    assert data["sha256"] == vr.sha256_text("# Indeks\n")


@pytest.mark.parametrize("bad", ["tajne.md", "../tajne.md", "/etc/passwd", "02-wiedza/../tajne.md",
                                 "02-wiedza/x.txt", "C:/x.md", "02-wiedza//x.md"])
def test_read_rejects_paths(vault, bad):
    assert make_client().get("/vault/note", query_string={"path": bad}).status_code == 400


def test_read_missing_is_404(vault):
    assert make_client().get("/vault/note?path=02-wiedza/Brak.md").status_code == 404


def test_find_matches_name_and_tags_only(vault):
    results = make_client().get("/vault/find?q=stare ai").get_json()["results"]
    assert results and results[0]["path"].endswith("Stare LLM.md") and "wiedza/ai" in results[0]["tags"]
    assert make_client().get("/vault/find?q=zzzz").get_json()["results"] == []
    assert make_client().get("/vault/find?q=a").status_code == 400


def test_apply_creates_note_and_appends_index(vault):
    client = make_client()
    base = vr.sha256_text("# Indeks\n")
    resp = apply(client, [
        {"path": NOTE, "content": BODY, "mode": "create"},
        {"path": vr.INDEX_PATH, "content": "- [[Nowa]]", "mode": "append", "base_sha256": base},
    ])
    assert resp.status_code == 200, resp.get_json()
    assert (vault / NOTE).read_text(encoding="utf-8") == BODY
    assert (vault / "02-wiedza" / "_index.md").read_text(encoding="utf-8") == "# Indeks\n- [[Nowa]]\n"
    assert len(resp.get_json()["written"]) == 2


def test_apply_never_overwrites_and_checks_nothing_written_on_conflict(vault):
    client = make_client()
    existing = "02-wiedza/Informatyka/Stare LLM.md"
    resp = apply(client, [
        {"path": NOTE, "content": BODY, "mode": "create"},
        {"path": existing, "content": BODY, "mode": "create"},
    ])
    assert resp.status_code == 409
    assert not (vault / NOTE).exists()  # all-or-nothing preconditions


def test_append_needs_matching_base_hash_and_index_only(vault):
    client = make_client()
    stale = apply(client, [{"path": vr.INDEX_PATH, "content": "x", "mode": "append", "base_sha256": "bad"}])
    assert stale.status_code == 409
    other = apply(client, [{"path": "02-wiedza/Informatyka/Stare LLM.md", "content": "x", "mode": "append",
                            "base_sha256": vr.sha256_text("x")}])
    assert other.status_code == 400
    missing_hash = apply(client, [{"path": vr.INDEX_PATH, "content": "x", "mode": "append"}])
    assert missing_hash.status_code == 409


@pytest.mark.parametrize("path", ["tajne.md", "../x.md", "02-wiedza/x.txt", "02-wiedza/_hidden.md",
                                  "02-wiedza/_index.md", "Journal/dzis.md", "02-wiedza/../x.md"])
def test_apply_rejects_bad_create_paths(vault, path):
    assert apply(make_client(), [{"path": path, "content": BODY, "mode": "create"}]).status_code in (400, 409)
    assert not (vault / "tajne.md").read_text(encoding="utf-8") != "tajne"


def test_apply_validates_package_shape(vault):
    client = make_client()
    assert apply(client, []).status_code == 400
    assert apply(client, [{"path": NOTE, "content": "  ", "mode": "create"}]).status_code == 400
    assert apply(client, [{"path": NOTE, "content": BODY, "mode": "weird"}]).status_code == 400
    dup = [{"path": NOTE, "content": BODY}, {"path": NOTE, "content": BODY}]
    assert apply(client, dup).status_code == 400


def test_error_messages_never_echo_the_supplied_path(vault):
    client = make_client()
    marker = "<script>zzz</script>/..//x.md"
    for resp in (
        client.get("/vault/note", query_string={"path": marker}),
        apply(client, [{"path": marker, "content": BODY, "mode": "create"}]),
        apply(client, [{"path": "02-wiedza/<b>zzz</b>.txt", "content": BODY, "mode": "create"}]),
    ):
        assert resp.status_code == 400
        assert "zzz" not in resp.get_data(as_text=True)


def test_write_failure_reports_partial_state(vault, monkeypatch):
    calls = []

    def boom(session, path, content, **kw):
        calls.append(path)
        if len(calls) == 2:
            raise OSError("disk")
        (vault / path).parent.mkdir(parents=True, exist_ok=True)
        (vault / path).write_text(content, encoding="utf-8")

    monkeypatch.setattr(vr, "write_note_with_version", boom)
    second = "02-wiedza/Informatyka/Druga.md"
    resp = apply(make_client(), [{"path": NOTE, "content": BODY}, {"path": second, "content": BODY}])
    assert resp.status_code == 500
    assert [w["index"] for w in resp.get_json()["written"]] == [0]
