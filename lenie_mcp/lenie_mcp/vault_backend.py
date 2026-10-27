"""Where the vault lives: local disk or the NAS copy behind the backend gateway (ADR-030 Etap A / A2).

Both backends expose the same four operations, so propose/commit logic and the tools do not care which one
is configured. `apply` receives the whole package as plain dicts
``{path, content, mode: create|append, base_sha256}`` and writes it all-or-nothing as far as preconditions go.
"""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
from typing import Protocol

from . import vault as vlt
from .client import LenieClient, LenieError
from .vault import VaultError


def sha256_text(text: str | None) -> str | None:
    return None if text is None else hashlib.sha256(text.encode("utf-8")).hexdigest()


class VaultBackend(Protocol):
    mode: str

    def read(self, path: str) -> str | None: ...

    def find(self, query: str, limit: int = 10) -> list[dict]: ...

    def apply(self, ops: list[dict]) -> list[str]: ...


class LocalVault:
    mode = "local"

    def __init__(self, root: Path):
        self.root = root

    def read(self, path: str) -> str | None:
        target = vlt.resolve_in_vault(self.root, path)
        return target.read_text(encoding="utf-8") if target.is_file() else None

    def find(self, query: str, limit: int = 10) -> list[dict]:
        return vlt.find_notes(self.root, query, limit)

    def apply(self, ops: list[dict]) -> list[str]:
        plan = []
        for op in ops:
            target = vlt.resolve_in_vault(self.root, op["path"])
            if op["mode"] == "create":
                plan.append((target, op["content"].rstrip("\n") + "\n", "x", op["path"]))
                continue
            existing = target.read_text(encoding="utf-8")
            if sha256_text(existing) != op.get("base_sha256"):
                raise VaultError(f"{op['path']}: file changed since the proposal")
            plan.append((target, existing.rstrip("\n") + "\n" + op["content"].rstrip("\n") + "\n", "replace", op["path"]))
        written = []
        for target, text, how, rel in plan:
            target.parent.mkdir(parents=True, exist_ok=True)
            if how == "x":
                with open(target, "x", encoding="utf-8", newline="\n") as fh:
                    fh.write(text)
            else:
                tmp = target.with_name(target.name + ".lenie-tmp")
                tmp.write_text(text, encoding="utf-8", newline="\n")
                os.replace(tmp, target)
            written.append(rel)
        return written


class RemoteVault:
    """The vault volume on the NAS, reached through GET /vault/note, GET /vault/find and POST /vault/apply."""

    mode = "remote"

    def __init__(self, client: LenieClient):
        self.client = client

    def read(self, path: str) -> str | None:
        try:
            return self.client.get("/vault/note", path=vlt.normalize_rel(path))["text"]
        except LenieError as exc:
            if exc.status == 404:
                return None
            raise VaultError(str(exc)) from None

    def find(self, query: str, limit: int = 10) -> list[dict]:
        try:
            return self.client.get("/vault/find", q=query, limit=limit)["results"]
        except LenieError as exc:
            raise VaultError(str(exc)) from None

    def apply(self, ops: list[dict]) -> list[str]:
        try:
            resp = self.client.post("/vault/apply", {"files": ops})
        except LenieError as exc:
            raise VaultError(str(exc)) from None
        return [ops[w["index"]]["path"] for w in resp.get("written", [])]
