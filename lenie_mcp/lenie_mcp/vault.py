"""Safe, bounded access to the Obsidian vault (ADR-030 D3/D5).

Every path is vault-relative and must resolve inside the vault (no absolute paths, no `..`, no
symlink/junction escapes). Reads are limited to NOTES_ROOT.
"""

from __future__ import annotations

import re
import unicodedata
from pathlib import Path

NOTES_ROOT = "02-wiedza"
INDEX_PATH = f"{NOTES_ROOT}/_index.md"
MAX_READ_CHARS = 40_000


class VaultError(RuntimeError):
    pass


def normalize_rel(rel: str) -> str:
    if not isinstance(rel, str) or not rel.strip() or "\x00" in rel:
        raise VaultError("path must be a non-empty string")
    norm = rel.replace("\\", "/").strip()
    if norm.startswith("/") or re.match(r"^[A-Za-z]:", norm):
        raise VaultError("path must be vault-relative")
    parts = norm.split("/")
    if any(p in ("..", "") for p in parts):
        raise VaultError("path must not contain '..' or empty segments")
    return "/".join(parts)


def resolve_in_vault(vault: Path, rel: str, *, under: str | None = NOTES_ROOT) -> Path:
    """Return the absolute path of `rel`, guaranteed to lie inside the vault (and under `under`)."""
    norm = normalize_rel(rel)
    if under and not (norm == under or norm.startswith(under + "/")):
        raise VaultError(f"path must be under {under}/")
    vault_real = vault.resolve()
    target = (vault_real / norm)
    # resolve(strict=False) follows symlinks/junctions of every existing ancestor
    real = target.resolve()
    if real != vault_real and vault_real not in real.parents:
        raise VaultError("path escapes the vault")
    if under:
        root_real = (vault_real / under).resolve()
        if real != root_real and root_real not in real.parents:
            raise VaultError(f"path escapes {under}/")
    return target


def read_note(vault: Path, rel: str, max_chars: int = MAX_READ_CHARS) -> dict:
    path = resolve_in_vault(vault, rel)
    if not path.is_file():
        raise VaultError("note not found")
    text = path.read_text(encoding="utf-8")
    return {
        "path": normalize_rel(rel),
        "text": text[:max_chars],
        "truncated": len(text) > max_chars,
        "total_chars": len(text),
    }


def _fold(s: str) -> str:
    s = s.casefold().replace("ł", "l")
    return "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c))


def _frontmatter_tags(text: str) -> list[str]:
    m = re.match(r"^---\r?\n(.*?)\r?\n---", text, re.DOTALL)
    if not m:
        return []
    return re.findall(r"wiedza/[\w\-/ąćęłńóśźżĄĆĘŁŃÓŚŹŻ]+", m.group(1))


def find_notes(vault: Path, query: str, limit: int = 10) -> list[dict]:
    """Match query words against file names and frontmatter tags only -- never full-text scans the vault."""
    words = [w for w in _fold(query).split() if len(w) >= 2]
    if not words:
        raise VaultError("query must contain at least one word of 2+ characters")
    limit = max(1, min(limit, 20))
    root = resolve_in_vault(vault, NOTES_ROOT)
    scored: list[tuple[int, str, list[str]]] = []
    for md in root.rglob("*.md"):
        if md.name.startswith("_"):
            continue
        rel = md.relative_to(vault.resolve()).as_posix()
        try:
            head = md.open(encoding="utf-8").read(2000)
        except OSError:
            continue
        tags = _frontmatter_tags(head)
        haystack = _fold(rel + " " + " ".join(tags))
        score = sum(1 for w in words if w in haystack)
        if score:
            scored.append((score, rel, tags))
    scored.sort(key=lambda t: (-t[0], t[1]))
    return [{"path": rel, "tags": tags, "score": score} for score, rel, tags in scored[:limit]]
