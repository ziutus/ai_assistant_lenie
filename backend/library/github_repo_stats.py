"""Public GitHub numbers (stars, forks, activity) for repositories Lenie knows about.

``GET https://api.github.com/repos/{owner}/{repo}`` needs no key, but is limited
to 60 requests per hour per IP; an optional ``GITHUB_TOKEN`` config key lifts it
to 5000. Reads never touch the network: list views take stored rows through
``stats_for_urls()`` and only ``refresh_stale()`` — an explicit user action —
calls GitHub, a bounded number of repositories at a time.
"""

import datetime
import logging
import re
from urllib.parse import urlparse

import requests
from sqlalchemy import select

from library.db.models import GithubRepoStats
from library.external_service_events import observed_request

logger = logging.getLogger(__name__)

API_URL = "https://api.github.com/repos/{owner}/{repo}"
REQUEST_TIMEOUT_S = 10
STALE_AFTER = datetime.timedelta(hours=24)
DEFAULT_REFRESH_LIMIT = 30
MAX_REFRESH_LIMIT = 60

_GITHUB_HOSTS = {"github.com", "www.github.com"}
_NAME_RE = re.compile(r"[A-Za-z0-9._-]+")
# First path segments of github.com that are site sections, not accounts.
_RESERVED_OWNERS = {
    "about", "apps", "collections", "enterprise", "events", "explore", "features", "issues", "login",
    "marketplace", "new", "notifications", "orgs", "organizations", "pricing", "pulls", "search",
    "security", "settings", "sponsors", "topics", "trending", "users",
}


class GithubError(Exception):
    """GitHub could not be queried (transport failure or an unexpected status)."""


class GithubRateLimited(GithubError):
    """GitHub's rate limit is exhausted; retry after the reset time."""


def parse_repo_url(url: str | None) -> tuple[str, str] | None:
    """``(owner, repo)`` of a ``github.com/owner/repo[/...]`` URL, else ``None``."""
    if not url or not url.strip():
        return None
    text = url.strip()
    parsed = urlparse(text if "://" in text else f"https://{text}")
    if (parsed.hostname or "").lower() not in _GITHUB_HOSTS:
        return None
    parts = [part for part in parsed.path.split("/") if part]
    if len(parts) < 2:
        return None
    owner, repo = parts[0], parts[1]
    if repo.endswith(".git"):
        repo = repo[:-4]
    if owner.lower() in _RESERVED_OWNERS or not _NAME_RE.fullmatch(owner) or not _NAME_RE.fullmatch(repo):
        return None
    return owner, repo


def repo_key(owner: str, repo: str) -> str:
    return f"{owner}/{repo}".lower()


def _token() -> str | None:
    try:
        from library.config_loader import load_config
        return load_config().get("GITHUB_TOKEN") or None
    except (Exception, SystemExit):  # the token is optional: never fail a refresh over config
        return None


def _parse_time(value: str | None) -> datetime.datetime | None:
    if not value:
        return None
    return datetime.datetime.fromisoformat(value.replace("Z", "+00:00"))


def fetch_repo(owner: str, repo: str) -> dict | None:
    """Raw repository JSON from GitHub, or ``None`` when the repository does not exist (404)."""
    headers = {"Accept": "application/vnd.github+json", "User-Agent": "lenie-server"}
    token = _token()
    if token:
        headers["Authorization"] = f"Bearer {token}"
    try:
        response = observed_request(
            service="github", operation="repo",
            request_fn=lambda: requests.get(
                API_URL.format(owner=owner, repo=repo), headers=headers, timeout=REQUEST_TIMEOUT_S,
            ),
            success_fn=lambda r: r.status_code in (200, 404),
        )
    except requests.RequestException as exc:
        raise GithubError(f"GitHub request failed: {exc}") from exc
    if response.status_code == 404:
        return None
    if response.status_code == 429 or (response.status_code == 403 and response.headers.get("X-RateLimit-Remaining") == "0"):
        raise GithubRateLimited(f"GitHub rate limit reached (HTTP {response.status_code})")
    if not response.ok:
        raise GithubError(f"GitHub answered HTTP {response.status_code}")
    try:
        return response.json()
    except ValueError as exc:
        raise GithubError(f"GitHub returned invalid JSON: {exc}") from exc


RATE_LIMIT_URL = "https://api.github.com/rate_limit"


def fetch_rate_limit() -> dict | None:
    """Current core quota from GitHub (``limit``, ``remaining``, ``reset`` ISO time, ``authenticated``).

    The ``/rate_limit`` endpoint itself is free - it does not use up the quota it reports. ``authenticated``
    says whether a ``GITHUB_TOKEN`` is configured; its value is never returned. ``None`` when GitHub is unreachable.
    """
    token = _token()
    headers = {"Accept": "application/vnd.github+json", "User-Agent": "lenie-server"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    try:
        response = requests.get(RATE_LIMIT_URL, headers=headers, timeout=REQUEST_TIMEOUT_S)
        core = response.json()["resources"]["core"] if response.ok else None
    except (requests.RequestException, ValueError, KeyError, TypeError):
        logger.warning("GitHub rate limit lookup failed", exc_info=True)
        return None
    if not core:
        return None
    reset = core.get("reset")
    return {
        "limit": core.get("limit"),
        "remaining": core.get("remaining"),
        "reset": datetime.datetime.fromtimestamp(reset, datetime.timezone.utc).isoformat() if isinstance(reset, int) else None,
        "authenticated": bool(token),
    }


def refresh_repo(session, owner: str, repo: str, now: datetime.datetime | None = None) -> GithubRepoStats:
    """Fetch one repository and upsert its row (no commit). A 404 keeps the last known numbers."""
    now = now or datetime.datetime.now(datetime.timezone.utc)
    data = fetch_repo(owner, repo)
    key = repo_key(owner, repo)
    row = session.execute(select(GithubRepoStats).where(GithubRepoStats.full_name_key == key)).scalars().first()
    if row is None:
        row = GithubRepoStats(full_name_key=key, owner=owner, repo=repo)
        session.add(row)
    row.fetched_at = now
    if data is None:
        row.status = "not_found"
        return row
    row.status = "ok"
    row.owner = (data.get("owner") or {}).get("login") or owner
    row.repo = data.get("name") or repo
    row.description = data.get("description")
    row.stars = data.get("stargazers_count")
    row.forks = data.get("forks_count")
    row.watchers = data.get("subscribers_count")
    row.open_issues = data.get("open_issues_count")
    row.language = data.get("language")
    row.license = (data.get("license") or {}).get("spdx_id")
    row.topics = [topic for topic in (data.get("topics") or []) if isinstance(topic, str)]
    row.archived = bool(data.get("archived"))
    row.repo_created_at = _parse_time(data.get("created_at"))
    row.pushed_at = _parse_time(data.get("pushed_at"))
    return row


def to_dict(row: GithubRepoStats) -> dict:
    return {
        "full_name": f"{row.owner}/{row.repo}",
        "status": row.status,
        "stars": row.stars,
        "forks": row.forks,
        "watchers": row.watchers,
        "open_issues": row.open_issues,
        "language": row.language,
        "license": row.license,
        "description": row.description,
        "topics": list(row.topics or []),
        "archived": row.archived,
        "pushed_at": row.pushed_at.isoformat() if row.pushed_at else None,
        "fetched_at": row.fetched_at.isoformat() if row.fetched_at else None,
    }


def stats_for_urls(session, urls) -> dict[str, dict]:
    """Stored stats keyed by the URL they were asked for; URLs that are not GitHub repos are absent."""
    wanted: dict[str, list[str]] = {}
    for url in urls:
        parsed = parse_repo_url(url)
        if parsed is not None:
            wanted.setdefault(repo_key(*parsed), []).append(url)
    if not wanted:
        return {}
    rows = session.execute(select(GithubRepoStats).where(GithubRepoStats.full_name_key.in_(list(wanted)))).scalars().all()
    result: dict[str, dict] = {}
    for row in rows:
        payload = to_dict(row)
        for url in wanted.get(row.full_name_key, []):
            result[url] = payload
    return result


def refresh_stale(session, urls, limit: int = DEFAULT_REFRESH_LIMIT, now: datetime.datetime | None = None,
                  force: bool = False) -> dict:
    """Refresh up to ``limit`` repositories behind ``urls`` that have no row yet or a row older than a day.

    Repositories never fetched go first. Stops at the first rate-limit answer;
    a single failing repository is counted and skipped. The caller commits.
    ``force`` ignores the one-day freshness rule (oldest rows first) - meant for a handful of
    repositories the caller picked by hand, not for a bulk run, which would keep re-fetching the same ones.
    """
    now = now or datetime.datetime.now(datetime.timezone.utc)
    repos: dict[str, tuple[str, str]] = {}
    for url in urls:
        parsed = parse_repo_url(url)
        if parsed is not None:
            repos.setdefault(repo_key(*parsed), parsed)
    existing = {
        row.full_name_key: row
        for row in session.execute(
            select(GithubRepoStats).where(GithubRepoStats.full_name_key.in_(list(repos)))
        ).scalars().all()
    } if repos else {}
    missing = [key for key in repos if key not in existing]
    stale = sorted(
        (key for key, row in existing.items() if force or row.fetched_at is None or now - row.fetched_at >= STALE_AFTER),
        key=lambda key: existing[key].fetched_at or now,
    )
    queue = missing + stale
    batch = queue[:max(0, limit)]
    refreshed = failed = 0
    rate_limited = False
    for key in batch:
        try:
            refresh_repo(session, *repos[key], now=now)
            refreshed += 1
        except GithubRateLimited:
            rate_limited = True
            break
        except GithubError:
            logger.warning("GitHub refresh failed for %s", key, exc_info=True)
            failed += 1
    return {
        "repositories": len(repos),
        "refreshed": refreshed,
        "failed": failed,
        "rate_limited": rate_limited,
        "pending": len(queue) - refreshed - failed,
    }
