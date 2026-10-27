"""Flask blueprint: narrow, service-key-only gateway to the NAS copy of the Obsidian vault (ADR-030 Etap A2).

The vault volume is kept in sync with Obsidian Sync by the ``obsidian-headless-sync`` container. The Lenie MCP
server uses these endpoints instead of a local vault path, so notes can be created from any machine (and later
from a tunnel) while Obsidian Sync spreads them to the user's devices.

Endpoints (all need a ``service`` API key):
  GET  /vault/note?path=<vault-relative .md under 02-wiedza>   -- content + sha256 (404 when missing)
  GET  /vault/find?q=<words>&limit=<n>                         -- file-name / frontmatter-tag match, no full-text scan
  POST /vault/apply  {"files": [{"path", "content", "mode": "create"|"append", "base_sha256"}]}

Deliberately narrow: only ``02-wiedza/``, only ``.md``, ``create`` never overwrites, ``append`` is accepted for
``02-wiedza/_index.md`` only and needs the sha256 of the file the caller based the addition on. All preconditions
for the whole package are checked before the first byte is written; every write goes through
``obsidian_vault.write_note_with_version`` (version row + atomic rename).
"""

from __future__ import annotations

import hashlib
import logging
import re
import threading
import unicodedata

from flask import Blueprint, abort, g, jsonify, request

from library.db.engine import get_scoped_session
from library.obsidian_vault import (
    VaultPathInvalidError,
    ensure_within_vault,
    read_note,
    write_note_with_version,
)

logger = logging.getLogger(__name__)

bp = Blueprint("obsidian_vault", __name__)

NOTES_ROOT = "02-wiedza"
INDEX_PATH = f"{NOTES_ROOT}/_index.md"
MAX_FILES = 10
MAX_FILE_CHARS = 60_000
MAX_NOTE_CHARS = 100_000
USER_PROMPT = "lenie_mcp /vault/apply"

# One writer at a time inside this process; cross-process races on the same path are additionally
# serialized by the advisory lock in write_note_with_version.
_apply_lock = threading.Lock()


def _service_only() -> None:
    if getattr(g, "auth", None) is None or g.auth.kind != "service":
        abort(403, "service API key required")


def normalize_path(path) -> str:
    if not isinstance(path, str) or not path.strip() or "\x00" in path:
        raise ValueError("path must be a non-empty string")
    norm = path.replace("\\", "/").strip()
    if norm.startswith("/") or re.match(r"^[A-Za-z]:", norm):
        raise ValueError("path must be vault-relative")
    parts = norm.split("/")
    if any(p in ("", "..") for p in parts):
        raise ValueError("path must not contain '..' or empty segments")
    if parts[0] != NOTES_ROOT:
        raise ValueError(f"path must be under {NOTES_ROOT}/")
    if not norm.endswith(".md"):
        raise ValueError("only .md files")
    return "/".join(parts)


def sha256_text(text: str | None) -> str | None:
    return None if text is None else hashlib.sha256(text.encode("utf-8")).hexdigest()


def _fold(s: str) -> str:
    s = s.casefold().replace("ł", "l")
    return "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c))


def _frontmatter_tags(head: str) -> list[str]:
    m = re.match(r"^---\r?\n(.*?)\r?\n---", head, re.DOTALL)
    return re.findall(r"wiedza/[\w\-/ąćęłńóśźżĄĆĘŁŃÓŚŹŻ]+", m.group(1)) if m else []


def _error(message: str, status: int = 400):
    return jsonify({"status": "error", "message": message}), status


@bp.route("/vault/note", methods=["GET"])
def vault_note():
    _service_only()
    try:
        path = normalize_path(request.args.get("path"))
        text = read_note(path)
    except (ValueError, VaultPathInvalidError) as exc:
        return _error(str(exc))
    if text is None:
        return _error("note not found", 404)
    return jsonify({"status": "success", "path": path, "text": text, "sha256": sha256_text(text)})


@bp.route("/vault/find", methods=["GET"])
def vault_find():
    _service_only()
    words = [w for w in _fold(request.args.get("q", "")).split() if len(w) >= 2]
    if not words:
        return _error("q must contain at least one word of 2+ characters")
    try:
        limit = max(1, min(int(request.args.get("limit", 10)), 20))
    except ValueError:
        return _error("limit must be an integer")
    vault_root = ensure_within_vault("")
    notes_root = ensure_within_vault(NOTES_ROOT)
    scored = []
    if notes_root.is_dir():
        for md in notes_root.rglob("*.md"):
            if md.name.startswith("_"):
                continue
            try:
                head = md.open(encoding="utf-8").read(2000)
            except OSError:
                continue
            rel = md.relative_to(vault_root).as_posix()
            tags = _frontmatter_tags(head)
            haystack = _fold(rel + " " + " ".join(tags))
            score = sum(1 for w in words if w in haystack)
            if score:
                scored.append((score, rel, tags))
    scored.sort(key=lambda t: (-t[0], t[1]))
    return jsonify({
        "status": "success",
        "results": [{"path": rel, "tags": tags, "score": score} for score, rel, tags in scored[:limit]],
    })


def _plan(files) -> list[dict] | tuple:
    """Validate the whole package against the current vault state. Returns the write plan or an error response."""
    if not isinstance(files, list) or not files or len(files) > MAX_FILES:
        return _error(f"files must be a list of 1..{MAX_FILES} items")
    plan, seen = [], set()
    for item in files:
        if not isinstance(item, dict):
            return _error("each file must be an object")
        try:
            path = normalize_path(item.get("path"))
        except ValueError as exc:
            return _error(f"{item.get('path')!r}: {exc}")
        mode, content = item.get("mode", "create"), item.get("content")
        if mode not in ("create", "append"):
            return _error(f"{path}: mode must be 'create' or 'append'")
        if not isinstance(content, str) or not content.strip() or len(content) > MAX_FILE_CHARS:
            return _error(f"{path}: content must be a non-empty string up to {MAX_FILE_CHARS} chars")
        if path in seen:
            return _error(f"{path}: duplicated in package")
        seen.add(path)
        try:
            existing = read_note(path)
        except VaultPathInvalidError as exc:
            return _error(f"{path}: {exc}")
        if mode == "create":
            if path == INDEX_PATH or path.rsplit("/", 1)[-1].startswith("_"):
                return _error(f"{path}: reserved file name")
            if existing is not None:
                return _error(f"{path}: file already exists (overwriting is not supported)", 409)
            new_text = content.rstrip("\n") + "\n"
        else:
            if path != INDEX_PATH:
                return _error(f"{path}: append is accepted for {INDEX_PATH} only")
            if existing is None:
                return _error(f"{path}: file does not exist", 404)
            if item.get("base_sha256") != sha256_text(existing):
                return _error(f"{path}: file changed since the proposal (base_sha256 mismatch)", 409)
            new_text = existing.rstrip("\n") + "\n" + content.rstrip("\n") + "\n"
        if len(new_text) > MAX_NOTE_CHARS:
            return _error(f"{path}: resulting file too large")
        plan.append({"path": path, "text": new_text})
    return plan


@bp.route("/vault/apply", methods=["POST", "OPTIONS"])
def vault_apply():
    if request.method == "OPTIONS":
        return jsonify({"status": "ok"}), 200
    _service_only()
    data = request.get_json(silent=True) or {}
    with _apply_lock:
        plan = _plan(data.get("files"))
        if isinstance(plan, tuple):
            return plan
        session = get_scoped_session()
        written = []
        try:
            for step in plan:
                write_note_with_version(session, step["path"], step["text"], user_prompt=USER_PROMPT)
                written.append({"path": step["path"], "sha256": sha256_text(step["text"])})
        except Exception:
            session.rollback()
            logger.exception("vault apply failed after %d of %d files", len(written), len(plan))
            return jsonify({
                "status": "error", "message": "vault write failed", "written": written,
            }), 500
    return jsonify({"status": "success", "written": written})
