"""Two-step write: immutable, server-held proposals validated before anything touches the vault (ADR-030 D3).

`propose` writes nothing. `commit` re-validates, checks that base files did not change, writes files,
and returns what was written so the caller can sync the database.
"""

from __future__ import annotations

import difflib
import hashlib
import os
import re
import secrets
import time
from dataclasses import dataclass, field
from pathlib import Path

from .vault import INDEX_PATH, NOTES_ROOT, VaultError, normalize_rel, resolve_in_vault

PROPOSAL_TTL_SECONDS = 30 * 60
MAX_FILES = 10
MAX_FILE_CHARS = 60_000
_CYRILLIC = re.compile("[Ѐ-ӿ]")
_FINANCE = re.compile(r"koszt|cen[ayęie]|finans|zwrot|\bUSD\b|\bPLN\b|\bEUR\b|[$€]|TODO: wątek finansowy", re.IGNORECASE)


class ProposalError(RuntimeError):
    pass


@dataclass(frozen=True)
class FileChange:
    path: str
    content: str
    mode: str  # "create" | "append"
    chunk_positions: tuple[int, ...] | None = None

    @property
    def is_index(self) -> bool:
        return self.path == INDEX_PATH


@dataclass
class Proposal:
    id: str
    doc_id: int
    doc_uuid: str
    run_id: int | None
    files: tuple[FileChange, ...]
    base_hashes: dict[str, str | None]
    warnings: list[str]
    created: float = field(default_factory=time.time)
    files_written: bool = False
    synced: bool = False
    written_paths: list[str] = field(default_factory=list)


def _sha(text: str | None) -> str | None:
    return None if text is None else hashlib.sha256(text.encode("utf-8")).hexdigest()


def _read_if_exists(path: Path) -> str | None:
    return path.read_text(encoding="utf-8") if path.is_file() else None


def parse_files(raw: list[dict]) -> tuple[FileChange, ...]:
    if not isinstance(raw, list) or not raw or len(raw) > MAX_FILES:
        raise ProposalError(f"files must be a list of 1..{MAX_FILES} items")
    out, seen = [], set()
    for item in raw:
        if not isinstance(item, dict):
            raise ProposalError("each file must be an object {path, content, mode, chunk_positions?}")
        try:
            path = normalize_rel(item.get("path"))
        except VaultError as exc:
            raise ProposalError(str(exc)) from None
        mode = item.get("mode", "create")
        content = item.get("content")
        positions = item.get("chunk_positions")
        if mode not in ("create", "append"):
            raise ProposalError(f"{path}: mode must be 'create' or 'append'")
        if not isinstance(content, str) or not content.strip() or len(content) > MAX_FILE_CHARS:
            raise ProposalError(f"{path}: content must be a non-empty string up to {MAX_FILE_CHARS} chars")
        if path in seen:
            raise ProposalError(f"{path}: duplicated in package")
        seen.add(path)
        if positions is not None:
            if not isinstance(positions, list) or not all(isinstance(p, int) and not isinstance(p, bool) for p in positions):
                raise ProposalError(f"{path}: chunk_positions must be a list of integers")
            positions = tuple(sorted(set(positions)))
        out.append(FileChange(path, content, mode, positions))
    return tuple(out)


def validate(vault: Path, files: tuple[FileChange, ...], doc_uuid: str) -> tuple[dict[str, str | None], list[str]]:
    """Hard validation (raises ProposalError) + soft editorial warnings. Returns (base_hashes, warnings)."""
    base: dict[str, str | None] = {}
    warnings: list[str] = []
    for f in files:
        try:
            abs_path = resolve_in_vault(vault, f.path)
        except VaultError as exc:
            raise ProposalError(f"{f.path}: {exc}") from None
        if not f.path.endswith(".md"):
            raise ProposalError(f"{f.path}: only .md files")
        existing = _read_if_exists(abs_path)
        base[f.path] = _sha(existing)
        if f.is_index:
            if f.mode != "append" or existing is None:
                raise ProposalError(f"{f.path}: the index can only be appended to (mode='append', file must exist)")
            if f.chunk_positions:
                raise ProposalError(f"{f.path}: the index has no chunk_positions")
            continue
        if f.mode != "create":
            raise ProposalError(f"{f.path}: notes are created, not appended (only {INDEX_PATH} accepts append)")
        if existing is not None:
            raise ProposalError(f"{f.path}: file already exists (overwriting is not supported)")
        if Path(f.path).name.startswith("_"):
            raise ProposalError(f"{f.path}: file names starting with '_' are reserved")
        fm = re.match(r"^---\r?\n(.*?)\r?\n---\r?\n", f.content, re.DOTALL)
        if not fm or "wiedza/" not in fm.group(1):
            raise ProposalError(f"{f.path}: frontmatter with a 'wiedza/...' tag is required")
        body = f.content[fm.end():]
        body_no_code = re.sub(r"```.*?```", "", body, flags=re.DOTALL)
        h1 = re.findall(r"^# \S", body_no_code, re.MULTILINE)
        if len(h1) != 1:
            raise ProposalError(f"{f.path}: exactly one H1 required (found {len(h1)})")
        if doc_uuid.lower() not in f.content.lower():
            raise ProposalError(f"{f.path}: source must contain the Lenie document UUID {doc_uuid}")
        if _CYRILLIC.search(f.content):
            warnings.append(f"{f.path}: contains Cyrillic characters (vault convention: transliterate)")
        if not _FINANCE.search(f.content):
            warnings.append(f"{f.path}: no financial thread (add one or 'TODO: wątek finansowy')")
    if not any(not f.is_index for f in files):
        raise ProposalError("package must contain at least one note")
    return base, warnings


def preview(vault: Path, files: tuple[FileChange, ...], limit: int = 6000) -> list[dict]:
    out = []
    for f in files:
        if f.mode == "append":
            existing = _read_if_exists(resolve_in_vault(vault, f.path)) or ""
            diff = "".join(difflib.unified_diff(
                existing.splitlines(True), (existing.rstrip("\n") + "\n" + f.content.rstrip("\n") + "\n").splitlines(True),
                fromfile=f.path, tofile=f.path, n=1))
            shown = diff
        else:
            shown = f.content
        out.append({
            "path": f.path, "mode": f.mode, "chars": len(f.content),
            "chunk_positions": list(f.chunk_positions) if f.chunk_positions is not None else None,
            "content_or_diff": shown[:limit], "truncated": len(shown) > limit,
        })
    return out


class ProposalStore:
    def __init__(self, ttl: float = PROPOSAL_TTL_SECONDS, clock=time.time):
        self._items: dict[str, Proposal] = {}
        self._ttl = ttl
        self._clock = clock

    def add(self, doc_id, doc_uuid, run_id, files, base, warnings) -> Proposal:
        self._purge()
        p = Proposal(secrets.token_urlsafe(12), doc_id, doc_uuid, run_id, files, base, warnings, created=self._clock())
        self._items[p.id] = p
        return p

    def get(self, proposal_id: str) -> Proposal:
        self._purge()
        p = self._items.get(proposal_id)
        if p is None:
            raise ProposalError("unknown or expired proposal_id -- propose again")
        return p

    def _purge(self):
        now = self._clock()
        for pid in [k for k, v in self._items.items() if now - v.created > self._ttl]:
            del self._items[pid]


def write_files(vault: Path, p: Proposal) -> list[str]:
    """Re-validate and write. All preconditions are checked before the first byte is written."""
    base, _ = validate(vault, p.files, p.doc_uuid)
    if base != p.base_hashes:
        raise ProposalError("vault files changed since the proposal -- propose again")
    plan = []
    for f in p.files:
        abs_path = resolve_in_vault(vault, f.path)
        if f.mode == "create":
            plan.append((abs_path, f.content.rstrip("\n") + "\n", "x"))
        else:
            existing = abs_path.read_text(encoding="utf-8")
            plan.append((abs_path, existing.rstrip("\n") + "\n" + f.content.rstrip("\n") + "\n", "replace"))
    written = []
    for (abs_path, text, how), f in zip(plan, p.files):
        abs_path.parent.mkdir(parents=True, exist_ok=True)
        if how == "x":
            with open(abs_path, "x", encoding="utf-8", newline="\n") as fh:
                fh.write(text)
        else:
            tmp = abs_path.with_name(abs_path.name + ".lenie-tmp")
            tmp.write_text(text, encoding="utf-8", newline="\n")
            os.replace(tmp, abs_path)
        written.append(f.path)
    return written


def sync_payload(p: Proposal) -> dict:
    notes = [
        {"path": f.path, "chunk_positions": list(f.chunk_positions) if f.chunk_positions else None}
        for f in p.files if not f.is_index
    ]
    return {"notes": notes, "run_id": p.run_id}


__all__ = [
    "NOTES_ROOT",
    "FileChange",
    "Proposal",
    "ProposalError",
    "ProposalStore",
    "parse_files",
    "preview",
    "sync_payload",
    "validate",
    "write_files",
]
