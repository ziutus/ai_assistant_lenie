"""Remote vault mode: the NAS gateway (/vault/*) instead of a local vault path (ADR-030 Etap A2)."""

import httpx
import pytest

from lenie_mcp import proposals as pr
from lenie_mcp.client import LenieClient
from lenie_mcp.config import ConfigError, Settings, load_settings
from lenie_mcp.service import LenieService
from lenie_mcp.vault import VaultError
from lenie_mcp.vault_backend import RemoteVault, sha256_text

UUID = "82112b28-7b88-439a-ab3c-fc2f14ad11cd"
NOTE = "02-wiedza/Informatyka/AI/AI Lokalnie/Koszt - remote.md"
GOOD = f"""---
tags:
  - wiedza/informatyka
---
# Koszt - remote

Mac Studio 9 499 USD.

Źródło: film, uuid {UUID}
"""


class FakeNas:
    """Minimal stand-in for the backend: Lenie document API + /vault/* gateway over an in-memory vault."""

    def __init__(self):
        self.files = {"02-wiedza/_index.md": "# Indeks\n", "02-wiedza/Stare.md": "---\ntags:\n  - wiedza/ai\n---\n# S\n"}
        self.applied = []
        self.sync_calls = 0

    def __call__(self, request: httpx.Request) -> httpx.Response:
        path, params = request.url.path, request.url.params
        if path == "/website_get":
            return httpx.Response(200, json={"id": 11176, "uuid": UUID, "title": "T", "is_private": False})
        if path == "/analysis_runs":
            return httpx.Response(200, json={"runs": [{"id": 253, "status": "reviewed"}]})
        if path == "/document/11176/obsidian_notes":
            self.sync_calls += 1
            return httpx.Response(200, json={"obsidian_note_paths": [], "reviewed_at": "t", "chunks_changed": 1})
        if path == "/vault/note":
            text = self.files.get(params["path"])
            if text is None:
                return httpx.Response(404, text="<html>not found</html>")
            return httpx.Response(200, json={"status": "success", "path": params["path"], "text": text})
        if path == "/vault/find":
            hits = [{"path": p, "tags": [], "score": 1} for p in self.files if params["q"].lower() in p.lower()]
            return httpx.Response(200, json={"status": "success", "results": hits})
        if path == "/vault/apply":
            body = request.read()
            import json
            files = json.loads(body)["files"]
            for f in files:
                if f["mode"] == "create" and f["path"] in self.files:
                    return httpx.Response(409, json={"message": "exists"})
                if f["mode"] == "append" and sha256_text(self.files[f["path"]]) != f["base_sha256"]:
                    return httpx.Response(409, json={"message": "base_sha256 mismatch"})
            for f in files:
                if f["mode"] == "create":
                    self.files[f["path"]] = f["content"].rstrip("\n") + "\n"
                else:
                    self.files[f["path"]] = self.files[f["path"]].rstrip("\n") + "\n" + f["content"].rstrip("\n") + "\n"
            self.applied.append([f["path"] for f in files])
            return httpx.Response(200, json={"status": "success", "written": [{"path": f["path"]} for f in files]})
        return httpx.Response(404, json={"message": "nope"})


@pytest.fixture
def remote():
    nas = FakeNas()
    settings = Settings("http://x", "k", None, "remote")
    svc = LenieService(settings, LenieClient(settings, httpx.MockTransport(nas)))
    assert isinstance(svc.vault, RemoteVault)
    return svc, nas


def package(**over):
    f = {"path": NOTE, "content": GOOD, "mode": "create", "chunk_positions": [1, 2]}
    f.update(over)
    return [f, {"path": "02-wiedza/_index.md", "content": "- [[Koszt - remote]]", "mode": "append"}]


def test_settings_default_mode_follows_vault_presence(tmp_path):
    assert load_settings({"LENIE_API_KEY": "k"}).vault_mode == "remote"
    assert load_settings({"LENIE_API_KEY": "k", "LENIE_OBSIDIAN_VAULT": str(tmp_path)}).vault_mode == "local"
    with pytest.raises(ConfigError):
        load_settings({"LENIE_API_KEY": "k", "LENIE_VAULT_MODE": "local"})
    with pytest.raises(ConfigError):
        load_settings({"LENIE_API_KEY": "k", "LENIE_VAULT_MODE": "weird"})
    forced = load_settings({"LENIE_API_KEY": "k", "LENIE_OBSIDIAN_VAULT": str(tmp_path), "LENIE_VAULT_MODE": "remote"})
    assert forced.vault_mode == "remote"


def test_remote_reads(remote):
    svc, _ = remote
    assert svc.obsidian_read_index()["data"]["text"] == "# Indeks\n"
    assert svc.obsidian_find_notes("stare")["data"][0]["path"] == "02-wiedza/Stare.md"
    with pytest.raises(VaultError):
        svc.obsidian_read_note("02-wiedza/Brak.md")


def test_remote_propose_then_commit(remote):
    svc, nas = remote
    prop = svc.propose_package(11176, package(), run_id=253)
    assert NOTE not in nas.files  # propose writes nothing
    report = svc.commit_package(prop["proposal_id"])
    assert report["status"] == "ok" and nas.sync_calls == 1
    assert nas.files[NOTE].startswith("---") and nas.files["02-wiedza/_index.md"].endswith("[[Koszt - remote]]\n")
    assert nas.applied == [[NOTE, "02-wiedza/_index.md"]]  # one request for the whole package


def test_remote_commit_conflict_when_index_changed(remote):
    svc, nas = remote
    pid = svc.propose_package(11176, package(), run_id=253)["proposal_id"]
    nas.files["02-wiedza/_index.md"] = "# zmienione na NAS\n"
    with pytest.raises(pr.ProposalError):
        svc.commit_package(pid)
    assert NOTE not in nas.files and nas.sync_calls == 0


def test_remote_rejects_existing_note_at_propose(remote):
    svc, _ = remote
    with pytest.raises(pr.ProposalError):
        svc.propose_package(11176, package(path="02-wiedza/Stare.md"), run_id=253)


def test_paths_outside_notes_root_rejected_before_any_request(remote):
    svc, nas = remote
    with pytest.raises(pr.ProposalError):
        svc.propose_package(11176, package(path="Journal/dzis.md"), run_id=253)
    assert nas.applied == []
