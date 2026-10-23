"""Public GitHub and GitLab numbers (stars, forks, activity) for repositories Lenie knows about.

``GET https://api.github.com/repos/{owner}/{repo}`` needs no key, but is limited
to 60 requests per hour per IP; an optional ``GITHUB_TOKEN`` config key lifts it
to 5000. GitLab (``gitlab.com`` or a self-hosted ``gitlab.<domain>``) answers
``GET https://{host}/api/v4/projects/{path}`` for public projects without a key.
Reads never touch the network: list views take stored rows through
``stats_for_urls()`` / ``combined_stats_for_entries()`` and only ``refresh_stale()`` — an
explicit user action — calls the providers, a bounded number of repositories at a time.
One tool may have several repositories (a GitLab original and its GitHub mirror): the
combined payload sums them and keeps the per-repository numbers under ``repositories``.
"""

import datetime
import ipaddress
import logging
import re
import socket
from dataclasses import dataclass
from urllib.parse import quote, urlparse

import requests
from sqlalchemy import select

from library.db.models import GithubRepoStats
from library.external_service_events import observed_request

logger = logging.getLogger(__name__)

API_URL = "https://api.github.com/repos/{owner}/{repo}"
GITLAB_API_URL = "https://{host}/api/v4/projects/{path}"
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


# First path segments of a GitLab host that are site sections, not groups.
_GITLAB_RESERVED = {
    "-", "admin", "api", "assets", "dashboard", "explore", "groups", "help", "profile", "projects", "search",
    "snippets", "uploads", "users",
}


class GithubError(Exception):
    """A provider (GitHub or GitLab) could not be queried (transport failure or an unexpected status)."""


class GithubRateLimited(GithubError):
    """The provider's rate limit is exhausted; retry after the reset time."""


@dataclass(frozen=True)
class RepoRef:
    """A repository on a supported host: ``key`` identifies its row in ``github_repo_stats``."""

    provider: str  # "github" | "gitlab"
    host: str
    path: str  # "owner/repo" (GitHub) or "group/subgroup/project" (GitLab)
    owner: str
    repo: str
    key: str

    @property
    def url(self) -> str:
        return f"https://{self.host}/{self.path}"


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


def _is_gitlab_host(host: str) -> bool:
    labels = host.split(".")
    return host == "gitlab.com" or (len(labels) >= 3 and labels[0] == "gitlab")


def _parse_gitlab_url(url: str | None) -> RepoRef | None:
    if not url or not url.strip():
        return None
    text = url.strip()
    parsed = urlparse(text if "://" in text else f"https://{text}")
    host = (parsed.hostname or "").lower()
    if parsed.scheme not in ("http", "https") or not _is_gitlab_host(host):
        return None
    parts = [part for part in parsed.path.split("/") if part]
    if "-" in parts:  # ".../project/-/tree/main": everything after "/-/" is a page inside the project
        parts = parts[:parts.index("-")]
    if len(parts) < 2 or parts[0].lower() in _GITLAB_RESERVED:
        return None
    if parts[-1].endswith(".git"):
        parts[-1] = parts[-1][:-4]
    if not all(_NAME_RE.fullmatch(part) for part in parts):
        return None
    path = "/".join(parts)
    return RepoRef("gitlab", host, path, "/".join(parts[:-1]), parts[-1], f"{host}/{path}".lower())


def parse_repository_url(url: str | None) -> RepoRef | None:
    """The GitHub or GitLab repository a URL points at, else ``None``."""
    github = parse_repo_url(url)
    if github is not None:
        owner, repo = github
        return RepoRef("github", "github.com", f"{owner}/{repo}", owner, repo, repo_key(owner, repo))
    return _parse_gitlab_url(url)


def repository_urls(*sources) -> list[str]:
    """Flatten URLs, ``[{url, label}]`` link lists and ``None`` into one ordered list without blanks or repeats."""
    result: list[str] = []
    for source in sources:
        for item in (source if isinstance(source, (list, tuple)) else [source]):
            url = item.get("url") if isinstance(item, dict) else item
            if isinstance(url, str) and url.strip() and url.strip() not in result:
                result.append(url.strip())
    return result


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


def _assert_public_host(host: str) -> None:
    """Refuse a host that resolves to a private/loopback/link-local address (the host comes from stored user data)."""
    try:
        addresses = {info[4][0] for info in socket.getaddrinfo(host, 443, proto=socket.IPPROTO_TCP)}
    except OSError as exc:
        raise GithubError(f"cannot resolve {host}: {exc}") from exc
    if not addresses or any(not ipaddress.ip_address(address).is_global for address in addresses):
        raise GithubError(f"{host} does not resolve to a public address")


def fetch_gitlab_repo(host: str, path: str) -> dict | None:
    """Raw project JSON from a GitLab host, or ``None`` when the project does not exist (404, also a private one)."""
    _assert_public_host(host)
    url = GITLAB_API_URL.format(host=host, path=quote(path, safe="")) + "?license=true"
    try:
        response = observed_request(
            service="gitlab", operation="repo",
            request_fn=lambda: requests.get(
                url, headers={"Accept": "application/json", "User-Agent": "lenie-server"},
                timeout=REQUEST_TIMEOUT_S, allow_redirects=False,
            ),
            success_fn=lambda r: r.status_code in (200, 404) or 300 <= r.status_code < 400,
        )
    except requests.RequestException as exc:
        raise GithubError(f"GitLab request failed: {exc}") from exc
    if response.status_code == 404 or 300 <= response.status_code < 400:
        # A redirect means the project moved or the host was retired (gitlab.tt-rss.org now points at GitHub):
        # the numbers there belong to another address, so this one has none and is never summed twice.
        return None
    if response.status_code == 429:
        raise GithubRateLimited(f"GitLab rate limit reached on {host}")
    if not response.ok:
        raise GithubError(f"GitLab answered HTTP {response.status_code}")
    try:
        return response.json()
    except ValueError as exc:
        raise GithubError(f"GitLab returned invalid JSON: {exc}") from exc


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
        row = GithubRepoStats(full_name_key=key, provider="github", host="github.com", owner=owner, repo=repo)
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


def refresh_gitlab_repo(session, host: str, path: str, now: datetime.datetime | None = None) -> GithubRepoStats:
    """Fetch one GitLab project and upsert its row (no commit). A 404 keeps the last known numbers."""
    now = now or datetime.datetime.now(datetime.timezone.utc)
    data = fetch_gitlab_repo(host, path)
    key = f"{host}/{path}".lower()
    row = session.execute(select(GithubRepoStats).where(GithubRepoStats.full_name_key == key)).scalars().first()
    if row is None:
        namespace, _, name = path.rpartition("/")
        row = GithubRepoStats(full_name_key=key, provider="gitlab", host=host, owner=namespace, repo=name)
        session.add(row)
    row.fetched_at = now
    if data is None:
        row.status = "not_found"
        return row
    row.status = "ok"
    row.owner = (data.get("namespace") or {}).get("full_path") or row.owner
    row.repo = data.get("path") or row.repo
    row.description = data.get("description")
    row.stars = data.get("star_count")
    row.forks = data.get("forks_count")
    row.watchers = None  # GitLab has no watcher count
    row.open_issues = data.get("open_issues_count")
    row.language = None  # GitLab serves languages from a separate endpoint; not worth a second request
    license_info = data.get("license") or {}
    row.license = license_info.get("nickname") or license_info.get("key")
    row.topics = [topic for topic in (data.get("topics") or []) if isinstance(topic, str)]
    row.archived = bool(data.get("archived"))
    row.repo_created_at = _parse_time(data.get("created_at"))
    row.pushed_at = _parse_time(data.get("last_activity_at"))
    return row


def to_dict(row: GithubRepoStats) -> dict:
    provider = getattr(row, "provider", None) or "github"
    host = getattr(row, "host", None) or "github.com"
    full_name = f"{row.owner}/{row.repo}" if provider == "github" else f"{host}/{row.owner}/{row.repo}"
    return {
        "full_name": full_name,
        "provider": provider,
        "host": host,
        "url": f"https://{host}/{row.owner}/{row.repo}",
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
    """Stored stats keyed by the URL they were asked for; URLs that are not GitHub/GitLab repos are absent."""
    wanted: dict[str, list[str]] = {}
    for url in urls:
        ref = parse_repository_url(url)
        if ref is not None:
            wanted.setdefault(ref.key, []).append(url)
    if not wanted:
        return {}
    rows = session.execute(select(GithubRepoStats).where(GithubRepoStats.full_name_key.in_(list(wanted)))).scalars().all()
    result: dict[str, dict] = {}
    for row in rows:
        payload = to_dict(row)
        for url in wanted.get(row.full_name_key, []):
            result[url] = payload
    return result


def _sum_known(values) -> int | None:
    known = [value for value in values if value is not None]
    return sum(known) if known else None


def _combine(repositories: list[dict]) -> dict:
    """One payload for several repositories of the same tool: sums plus the per-repository list."""
    first = repositories[0]
    pushed = [r["pushed_at"] for r in repositories if r["pushed_at"]]
    fetched = [r["fetched_at"] for r in repositories if r["fetched_at"]]
    topics: list[str] = []
    for repository in repositories:
        topics.extend(topic for topic in repository["topics"] if topic not in topics)
    return {
        "full_name": first["full_name"],
        "provider": first["provider"],
        "host": first["host"],
        "url": first["url"],
        "status": "ok" if any(r["status"] == "ok" for r in repositories) else "not_found",
        "stars": _sum_known(r["stars"] for r in repositories),
        "forks": _sum_known(r["forks"] for r in repositories),
        "watchers": _sum_known(r["watchers"] for r in repositories),
        "open_issues": _sum_known(r["open_issues"] for r in repositories),
        "language": next((r["language"] for r in repositories if r["language"]), None),
        "license": next((r["license"] for r in repositories if r["license"]), None),
        "description": next((r["description"] for r in repositories if r["description"]), None),
        "topics": topics,
        "archived": all(r["archived"] for r in repositories),
        "pushed_at": max(pushed) if pushed else None,
        "fetched_at": min(fetched) if fetched else None,  # the oldest repository decides when a refresh is due
        "repositories": repositories,
    }


def combined_stats_for_entries(session, entries: dict) -> dict:
    """Stored stats of every repository of each entry, summed; entries without a stored row are absent.

    ``entries`` maps any key (a radar id, a tool id) to the URLs that may be repositories (homepage, links).
    The same repository named twice for one entry counts once; a GitLab original plus its GitHub mirror
    are two repositories and are both summed (their ``repositories`` breakdown shows where numbers come from).
    """
    refs: dict = {}
    for key, urls in entries.items():
        ordered: list[RepoRef] = []
        for url in urls:
            ref = parse_repository_url(url)
            if ref is not None and all(ref.key != other.key for other in ordered):
                ordered.append(ref)
        if ordered:
            refs[key] = ordered
    if not refs:
        return {}
    wanted = {ref.key for ordered in refs.values() for ref in ordered}
    rows = {
        row.full_name_key: row
        for row in session.execute(
            select(GithubRepoStats).where(GithubRepoStats.full_name_key.in_(list(wanted)))
        ).scalars().all()
    }
    result: dict = {}
    for key, ordered in refs.items():
        payloads = [to_dict(rows[ref.key]) for ref in ordered if ref.key in rows]
        if payloads:
            result[key] = _combine(payloads)
    return result


def refresh_stale(session, urls, limit: int = DEFAULT_REFRESH_LIMIT, now: datetime.datetime | None = None,
                  force: bool = False) -> dict:
    """Refresh up to ``limit`` GitHub/GitLab repositories behind ``urls`` that have no row yet or a row older than a day.

    Repositories never fetched go first. Stops at the first rate-limit answer;
    a single failing repository is counted and skipped. The caller commits.
    ``force`` ignores the one-day freshness rule (oldest rows first) - meant for a handful of
    repositories the caller picked by hand, not for a bulk run, which would keep re-fetching the same ones.
    """
    now = now or datetime.datetime.now(datetime.timezone.utc)
    repos: dict[str, RepoRef] = {}
    for url in urls:
        ref = parse_repository_url(url)
        if ref is not None:
            repos.setdefault(ref.key, ref)
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
        ref = repos[key]
        try:
            if ref.provider == "github":
                refresh_repo(session, ref.owner, ref.repo, now=now)
            else:
                refresh_gitlab_repo(session, ref.host, ref.path, now=now)
            refreshed += 1
        except GithubRateLimited:
            rate_limited = True
            break
        except GithubError:
            logger.warning("Repository refresh failed for %s", key, exc_info=True)
            failed += 1
    return {
        "repositories": len(repos),
        "refreshed": refreshed,
        "failed": failed,
        "rate_limited": rate_limited,
        "pending": len(queue) - refreshed - failed,
    }
