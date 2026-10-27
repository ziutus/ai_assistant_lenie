import json
from pathlib import Path

import httpx
import pytest

from lenie_mcp import proposals as pr
from lenie_mcp import vault as vlt
from lenie_mcp.client import LenieClient, LenieError
from lenie_mcp.config import ConfigError, Settings, load_settings
from lenie_mcp.service import LenieService

UUID = "82112b28-7b88-439a-ab3c-fc2f14ad11cd"
NOTE = "02-wiedza/Technologia/Lokalne LLM - koszt.md"
GOOD = f"""---
tags:
  - wiedza/technologia
---
# Lokalne LLM - koszt

Mac Studio ok. 9 499 USD kontra serwer 5 899 USD.

Źródło: film, uuid {UUID}
"""


@pytest.fixture
def vault(tmp_path: Path) -> Path:
    (tmp_path / "02-wiedza").mkdir()
    (tmp_path / "02-wiedza" / "_index.md").write_text("# Indeks\n", encoding="utf-8")
    (tmp_path / "02-wiedza" / "Stare.md").write_text("---\ntags:\n  - wiedza/ai\n---\n# Stare\n", encoding="utf-8")
    (tmp_path / "secret.md").write_text("tajne", encoding="utf-8")
    return tmp_path


class FakeApi:
    def __init__(self, private=False, sync_fails=0):
        self.calls, self.private, self.sync_fails = [], private, sync_fails

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.calls.append((request.method, request.url.path, request.url.params.get("positions")))
        assert request.headers["x-api-key"] == "k"
        path = request.url.path
        if path == "/website_get":
            body = {"id": 11176, "uuid": UUID, "title": "Sprzęt", "is_private": self.private,
                    "processing_status": "EMBEDDING_EXIST", "document_type": "youtube"}
            if request.url.params.get("include_text") != "0":
                body["text"] = "a" * 25
            return httpx.Response(200, json=body)
        if path == "/document/11176/readiness":
            return httpx.Response(200, json={"verdict": "ready", "steps": []})
        if path == "/analysis_runs":
            return httpx.Response(200, json={"runs": [{"id": 253, "status": "reviewed"}, {"id": 9, "status": "superseded"}]})
        if path == "/analysis_run/253/chunks":
            return httpx.Response(200, json={"segments": ["x" * 1000], "chunks": [
                {"position": 0, "type": "TEMAT", "status": "approved", "original_text": "abc", "topic": None}]})
        if path == "/document/11176/obsidian_notes":
            if self.sync_fails:
                self.sync_fails -= 1
                return httpx.Response(500, json={"message": "DB error"})
            return httpx.Response(200, json={"obsidian_note_paths": [NOTE], "reviewed_at": "t", "chunks_changed": 2})
        return httpx.Response(404, json={"message": "nope"})


def make(vault, **kw):
    api = FakeApi(**kw)
    settings = Settings("http://x", "k", vault)
    return LenieService(settings, LenieClient(settings, httpx.MockTransport(api))), api


# ---- config / vault ---------------------------------------------------
def test_config_requires_key(tmp_path):
    with pytest.raises(ConfigError):
        load_settings({})
    s = load_settings({"LENIE_API_KEY": "k", "LENIE_OBSIDIAN_VAULT": str(tmp_path)})
    assert s.vault == tmp_path.resolve() and s.api_url.startswith("http")


@pytest.mark.parametrize("bad", ["../secret.md", "/etc/passwd", "C:/x.md", "02-wiedza/../secret.md", "secret.md", "", "02-wiedza//x.md"])
def test_vault_rejects_bad_paths(vault, bad):
    with pytest.raises(vlt.VaultError):
        vlt.resolve_in_vault(vault, bad)


def test_vault_read_and_find(vault):
    assert "Stare" in vlt.read_note(vault, "02-wiedza/Stare.md")["text"]
    found = vlt.find_notes(vault, "stare")
    assert found and found[0]["path"] == "02-wiedza/Stare.md" and "wiedza/ai" in found[0]["tags"]
    assert vlt.find_notes(vault, "zzzz") == []


# ---- reads --------------------------------------------------------------
def test_get_document_wraps_untrusted_and_has_readiness(vault):
    svc, _ = make(vault)
    out = svc.get_document(11176)
    assert "untrusted" in out["notice"] and out["data"]["uuid"] == UUID
    assert out["data"]["readiness"]["verdict"] == "ready"


def test_text_paging_and_private_gate(vault):
    svc, _ = make(vault)
    page = svc.get_document_text(11176, offset=0, max_chars=10)["data"]
    assert len(page["text"]) == 10 and page["has_more"] and page["next_offset"] == 10
    private, _ = make(vault, private=True)
    with pytest.raises(LenieError):
        private.get_document_text(11176)
    assert private.get_document_text(11176, allow_private=True)["data"]["total_chars"] == 25


def test_chunks_drop_segments(vault):
    svc, api = make(vault)
    out = svc.get_chunks(253, positions=[0])["data"]
    assert out["chunks"][0]["text"] == "abc" and "segments" not in out
    assert api.calls[-1][2] == "0"


def test_client_errors_do_not_leak_key(vault):
    svc, _ = make(vault)
    with pytest.raises(LenieError) as e:
        svc.client.get("/missing")
    assert "k" != str(e.value) and "x-api-key" not in str(e.value)


# ---- propose / commit -----------------------------------------------------
def files(**over):
    f = {"path": NOTE, "content": GOOD, "mode": "create", "chunk_positions": [0, 1]}
    f.update(over)
    return [f, {"path": "02-wiedza/_index.md", "content": "- [[Lokalne LLM - koszt]]", "mode": "append"}]


def test_propose_writes_nothing_and_commit_writes_and_syncs(vault):
    svc, api = make(vault)
    prop = svc.propose_package(11176, files(), run_id=253)
    assert not (vault / NOTE).exists()
    assert prop["database_effects"]["notes"] == [{"path": NOTE, "chunk_positions": [0, 1]}]
    assert not prop["warnings"]
    report = svc.commit_package(prop["proposal_id"])
    assert report["status"] == "ok" and report["database"]["chunks_changed"] == 2
    assert (vault / NOTE).read_text(encoding="utf-8").startswith("---")
    assert (vault / "02-wiedza" / "_index.md").read_text(encoding="utf-8").endswith("[[Lokalne LLM - koszt]]\n")
    sync = [c for c in api.calls if c[1].endswith("/obsidian_notes")]
    assert len(sync) == 1


def test_commit_retry_only_syncs_after_db_failure(vault):
    svc, api = make(vault, sync_fails=1)
    pid = svc.propose_package(11176, files(), run_id=253)["proposal_id"]
    first = svc.commit_package(pid)
    assert first["status"] == "partial" and (vault / NOTE).exists()
    second = svc.commit_package(pid)
    assert second["status"] == "ok"
    assert len([c for c in api.calls if c[1].endswith("/obsidian_notes")]) == 2


def test_commit_detects_changed_base_and_unknown_id(vault):
    svc, _ = make(vault)
    pid = svc.propose_package(11176, files(), run_id=253)["proposal_id"]
    (vault / "02-wiedza" / "_index.md").write_text("# zmienione\n", encoding="utf-8")
    with pytest.raises(pr.ProposalError):
        svc.commit_package(pid)
    assert not (vault / NOTE).exists()
    with pytest.raises(pr.ProposalError):
        svc.commit_package("nope")


@pytest.mark.parametrize("over", [
    {"path": "../x.md"}, {"path": "02-wiedza/x.txt"}, {"path": "02-wiedza/_hidden.md"},
    {"path": "02-wiedza/Stare.md"},                       # exists
    {"content": GOOD.replace(UUID, "other-uuid")},        # wrong UUID
    {"content": GOOD.replace("wiedza/technologia", "x")}, # no tag
    {"content": GOOD + "\n# Drugi H1\n"},
    {"mode": "append"},                                   # notes cannot be appended
])
def test_validation_rejects(vault, over):
    svc, _ = make(vault)
    with pytest.raises(pr.ProposalError):
        svc.propose_package(11176, files(**over), run_id=253)


def test_run_must_be_active_and_positions_need_run(vault):
    svc, _ = make(vault)
    with pytest.raises(pr.ProposalError):
        svc.propose_package(11176, files(), run_id=9)
    with pytest.raises(pr.ProposalError):
        svc.propose_package(11176, files(), run_id=None)


def test_editorial_warnings_not_blocking(vault):
    svc, _ = make(vault)
    content = GOOD.replace("Mac Studio ok. 9 499 USD kontra serwer 5 899 USD.", "Тест").replace("koszt", "temat")
    out = svc.propose_package(11176, files(content=content, chunk_positions=None))
    assert any("Cyrillic" in w for w in out["warnings"]) and any("financial" in w for w in out["warnings"])


def test_proposal_expires(vault):
    t = [0.0]
    svc, _ = make(vault)
    svc.store = pr.ProposalStore(ttl=10, clock=lambda: t[0])
    pid = svc.propose_package(11176, files(), run_id=253)["proposal_id"]
    t[0] = 11
    with pytest.raises(pr.ProposalError):
        svc.commit_package(pid)


def test_server_registers_tools(vault):
    from lenie_mcp.server import build_server
    svc, _ = make(vault)
    mcp = build_server(svc)
    import asyncio
    tools = asyncio.run(mcp.list_tools())
    names = {t.name for t in (tools.tools if hasattr(tools, "tools") else tools)}
    assert {"lenie_get_document", "obsidian_propose_package", "obsidian_commit_package"} <= names
    json.dumps(sorted(names))
