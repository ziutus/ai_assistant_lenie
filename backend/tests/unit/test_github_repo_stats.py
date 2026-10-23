import datetime as dt
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

pytest.importorskip("sqlalchemy")

from flask import Flask, g

from library import github_repo_stats as svc

NOW = dt.datetime(2026, 10, 22, 12, 0, tzinfo=dt.timezone.utc)

GITHUB_JSON = {
    "name": "gaianet-node",
    "owner": {"login": "GaiaNet-AI"},
    "description": "Install, run and deploy your own decentralized AI agent service",
    "stargazers_count": 5018,
    "forks_count": 325,
    "subscribers_count": 38,
    "open_issues_count": 60,
    "language": "Shell",
    "license": {"spdx_id": "GPL-3.0"},
    "archived": False,
    "created_at": "2024-03-06T10:57:45Z",
    "pushed_at": "2025-10-13T03:27:09Z",
}


class TestParseRepoUrl:
    @pytest.mark.parametrize("url, expected", [
        ("https://github.com/GaiaNet-AI/gaianet-node", ("GaiaNet-AI", "gaianet-node")),
        ("https://www.github.com/owner/repo/", ("owner", "repo")),
        ("github.com/owner/repo", ("owner", "repo")),
        ("https://github.com/owner/repo.git", ("owner", "repo")),
        ("https://github.com/owner/repo/tree/main/docs?x=1#readme", ("owner", "repo")),
        ("  https://github.com/owner/dotted.repo  ", ("owner", "dotted.repo")),
    ])
    def test_repository_urls(self, url, expected):
        assert svc.parse_repo_url(url) == expected

    @pytest.mark.parametrize("url", [
        None, "", "   ", "https://example.com/owner/repo", "https://notgithub.com/owner/repo",
        "https://github.com/owner", "https://github.com/", "https://github.com/topics/python",
        "https://github.com/sponsors/someone", "https://gist.github.com/owner/abc",
        "https://github.com/ow ner/repo",
    ])
    def test_not_a_repository(self, url):
        assert svc.parse_repo_url(url) is None


class TestRefreshRepo:
    def test_maps_github_fields_onto_a_new_row(self, monkeypatch):
        monkeypatch.setattr(svc, "fetch_repo", lambda owner, repo: GITHUB_JSON)
        session = MagicMock()
        session.execute.return_value.scalars.return_value.first.return_value = None

        row = svc.refresh_repo(session, "gaianet-ai", "GAIANET-NODE", now=NOW)

        session.add.assert_called_once_with(row)
        assert row.full_name_key == "gaianet-ai/gaianet-node"
        assert (row.owner, row.repo) == ("GaiaNet-AI", "gaianet-node")  # canonical case comes from GitHub
        assert (row.stars, row.forks, row.watchers, row.open_issues) == (5018, 325, 38, 60)
        assert (row.language, row.license, row.archived, row.status) == ("Shell", "GPL-3.0", False, "ok")
        assert row.pushed_at == dt.datetime(2025, 10, 13, 3, 27, 9, tzinfo=dt.timezone.utc)
        assert row.fetched_at == NOW

    def test_stores_the_topics_and_ignores_junk_entries(self, monkeypatch):
        monkeypatch.setattr(svc, "fetch_repo", lambda owner, repo: {**GITHUB_JSON, "topics": ["sbom", "containers", None, 3]})
        session = MagicMock()
        session.execute.return_value.scalars.return_value.first.return_value = None

        row = svc.refresh_repo(session, "o", "r", now=NOW)

        assert row.topics == ["sbom", "containers"]
        payload = svc.to_dict(SimpleNamespace(
            owner="o", repo="r", status="ok", stars=1, forks=0, watchers=0, open_issues=0, language=None, license=None,
            archived=False, pushed_at=None, fetched_at=None, description=row.description, topics=row.topics,
        ))
        assert payload["topics"] == ["sbom", "containers"]
        assert payload["description"].startswith("Install, run")

    def test_a_repository_without_topics_gets_an_empty_list(self, monkeypatch):
        monkeypatch.setattr(svc, "fetch_repo", lambda owner, repo: GITHUB_JSON)  # the key is absent
        session = MagicMock()
        session.execute.return_value.scalars.return_value.first.return_value = None

        assert svc.refresh_repo(session, "o", "r", now=NOW).topics == []

    def test_not_found_keeps_the_last_known_numbers(self, monkeypatch):
        monkeypatch.setattr(svc, "fetch_repo", lambda owner, repo: None)
        existing = SimpleNamespace(stars=10, status="ok", fetched_at=None)
        session = MagicMock()
        session.execute.return_value.scalars.return_value.first.return_value = existing

        row = svc.refresh_repo(session, "o", "r", now=NOW)

        assert row is existing
        assert (row.status, row.stars, row.fetched_at) == ("not_found", 10, NOW)
        session.add.assert_not_called()


class TestFetchRepo:
    def _response(self, status, headers=None, payload=None):
        return SimpleNamespace(
            status_code=status, headers=headers or {}, ok=200 <= status < 300, json=lambda: payload,
        )

    def _patch(self, monkeypatch, response):
        monkeypatch.setattr(svc, "_token", lambda: None)
        monkeypatch.setattr(svc, "observed_request", lambda *, service, operation, request_fn, success_fn=None: response)

    def test_ok(self, monkeypatch):
        self._patch(monkeypatch, self._response(200, payload=GITHUB_JSON))
        assert svc.fetch_repo("o", "r") == GITHUB_JSON

    def test_404_is_none(self, monkeypatch):
        self._patch(monkeypatch, self._response(404))
        assert svc.fetch_repo("o", "r") is None

    def test_exhausted_limit_is_rate_limited(self, monkeypatch):
        self._patch(monkeypatch, self._response(403, headers={"X-RateLimit-Remaining": "0"}))
        with pytest.raises(svc.GithubRateLimited):
            svc.fetch_repo("o", "r")

    def test_other_403_is_a_plain_error(self, monkeypatch):
        self._patch(monkeypatch, self._response(403, headers={"X-RateLimit-Remaining": "12"}))
        with pytest.raises(svc.GithubError) as excinfo:
            svc.fetch_repo("o", "r")
        assert not isinstance(excinfo.value, svc.GithubRateLimited)


def _stored(key, fetched_at):
    return SimpleNamespace(full_name_key=key, fetched_at=fetched_at)


class TestFetchRateLimit:
    def _patch(self, monkeypatch, response=None, error=None, token="secret-token"):
        seen = {}

        def fake_get(url, headers=None, timeout=None):
            seen.update(url=url, headers=headers)
            if error:
                raise error
            return response

        monkeypatch.setattr(svc.requests, "get", fake_get)
        monkeypatch.setattr(svc, "_token", lambda: token)
        return seen

    def _response(self, payload, ok=True):
        return SimpleNamespace(ok=ok, json=lambda: payload)

    def test_reads_the_core_quota_and_never_returns_the_token(self, monkeypatch):
        payload = {"resources": {"core": {"limit": 5000, "remaining": 4987, "reset": 1792776830}}}
        seen = self._patch(monkeypatch, self._response(payload))

        rate = svc.fetch_rate_limit()

        assert rate == {"limit": 5000, "remaining": 4987, "reset": "2026-10-23T17:33:50+00:00", "authenticated": True}
        assert seen["headers"]["Authorization"] == "Bearer secret-token"
        assert "secret-token" not in str(rate)

    def test_without_a_token_the_request_is_anonymous(self, monkeypatch):
        payload = {"resources": {"core": {"limit": 60, "remaining": 60, "reset": 1792776830}}}
        seen = self._patch(monkeypatch, self._response(payload), token=None)

        rate = svc.fetch_rate_limit()

        assert rate["authenticated"] is False and rate["limit"] == 60
        assert "Authorization" not in seen["headers"]

    @pytest.mark.parametrize("response, error", [
        (None, svc.requests.ConnectionError("down")),
        (SimpleNamespace(ok=False, json=lambda: {}), None),
        (SimpleNamespace(ok=True, json=lambda: {"unexpected": 1}), None),
        (SimpleNamespace(ok=True, json=lambda: (_ for _ in ()).throw(ValueError("bad json"))), None),
    ])
    def test_unreachable_or_odd_answers_give_none(self, monkeypatch, response, error):
        self._patch(monkeypatch, response, error)
        assert svc.fetch_rate_limit() is None


class TestRefreshStale:
    def _session(self, existing):
        session = MagicMock()
        session.execute.return_value.scalars.return_value.all.return_value = existing
        return session

    def test_missing_first_then_oldest_and_fresh_ones_skipped(self, monkeypatch):
        calls = []
        monkeypatch.setattr(svc, "refresh_repo", lambda session, owner, repo, now=None: calls.append(f"{owner}/{repo}"))
        existing = [
            _stored("a/fresh", NOW - dt.timedelta(hours=1)),
            _stored("a/old", NOW - dt.timedelta(days=3)),
            _stored("a/older", NOW - dt.timedelta(days=9)),
        ]
        urls = [f"https://github.com/a/{name}" for name in ("fresh", "old", "older", "new")] + ["https://example.com/x"]

        summary = svc.refresh_stale(self._session(existing), urls, limit=10, now=NOW)

        assert calls == ["a/new", "a/older", "a/old"]
        assert summary == {"repositories": 4, "refreshed": 3, "failed": 0, "rate_limited": False, "pending": 0}

    def test_force_refreshes_a_fresh_row_too(self, monkeypatch):
        calls = []
        monkeypatch.setattr(svc, "refresh_repo", lambda session, owner, repo, now=None: calls.append(f"{owner}/{repo}"))
        existing = [_stored("a/fresh", NOW - dt.timedelta(minutes=5))]
        urls = ["https://github.com/a/fresh"]

        assert svc.refresh_stale(self._session(existing), urls, limit=10, now=NOW)["refreshed"] == 0
        summary = svc.refresh_stale(self._session(existing), urls, limit=10, now=NOW, force=True)

        assert calls == ["a/fresh"]
        assert summary["refreshed"] == 1 and summary["pending"] == 0

    def test_limit_leaves_the_rest_pending(self, monkeypatch):
        monkeypatch.setattr(svc, "refresh_repo", lambda *args, **kwargs: None)
        urls = [f"https://github.com/a/r{i}" for i in range(5)]

        summary = svc.refresh_stale(self._session([]), urls, limit=2, now=NOW)

        assert (summary["refreshed"], summary["pending"]) == (2, 3)

    def test_stops_at_rate_limit_and_counts_failures(self, monkeypatch):
        outcomes = iter([None, svc.GithubError("boom"), svc.GithubRateLimited("slow down"), None])

        def fake(session, owner, repo, now=None):
            outcome = next(outcomes)
            if outcome is not None:
                raise outcome

        monkeypatch.setattr(svc, "refresh_repo", fake)
        urls = [f"https://github.com/a/r{i}" for i in range(4)]

        summary = svc.refresh_stale(self._session([]), urls, limit=10, now=NOW)

        assert summary == {"repositories": 4, "refreshed": 1, "failed": 1, "rate_limited": True, "pending": 2}

    def test_no_github_urls_means_no_query(self):
        session = MagicMock()
        summary = svc.refresh_stale(session, [None, "https://example.com/x"], now=NOW)
        session.execute.assert_not_called()
        assert summary["repositories"] == 0 and summary["pending"] == 0


class TestStatsForUrls:
    def test_maps_back_to_the_requested_url_spelling(self):
        row = SimpleNamespace(
            full_name_key="gaianet-ai/gaianet-node", owner="GaiaNet-AI", repo="gaianet-node", status="ok",
            stars=5018, forks=325, watchers=38, open_issues=60, language="Shell", license="GPL-3.0",
            archived=False, pushed_at=NOW, fetched_at=NOW, description="Run your own AI agent", topics=["ai", "node"],
        )
        session = MagicMock()
        session.execute.return_value.scalars.return_value.all.return_value = [row]
        url = "https://github.com/gaianet-ai/GaiaNet-Node/"

        result = svc.stats_for_urls(session, [url, "https://example.com/x", None])

        assert list(result) == [url]
        assert result[url]["full_name"] == "GaiaNet-AI/gaianet-node"
        assert (result[url]["stars"], result[url]["forks"]) == (5018, 325)
        assert result[url]["topics"] == ["ai", "node"]
        assert result[url]["description"] == "Run your own AI agent"

    def test_nothing_to_look_up(self):
        session = MagicMock()
        assert svc.stats_for_urls(session, ["https://example.com/x"]) == {}
        session.execute.assert_not_called()


class TestRefreshEndpoint:
    def _call(self, monkeypatch, body, kind="user"):
        from library.tool_recommendation_routes import refresh_github_stats

        session = MagicMock()
        session.execute.return_value.all.return_value = [("https://github.com/a/b", [])]
        monkeypatch.setattr("library.tool_recommendation_routes.get_scoped_session", lambda: session)
        seen = {}

        def fake_refresh(sess, urls, limit):
            seen.update(urls=list(urls), limit=limit)
            return {"repositories": 1, "refreshed": 1, "failed": 0, "rate_limited": False, "pending": 0}

        monkeypatch.setattr(svc, "refresh_stale", fake_refresh)
        app = Flask(__name__)
        with app.test_request_context("/tool_recommendations/github_stats/refresh", method="POST", json=body):
            g.auth = SimpleNamespace(kind=kind, user_id=1)
            response = refresh_github_stats()
        return response, seen, session

    def test_refreshes_and_commits(self, monkeypatch):
        response, seen, session = self._call(monkeypatch, {"limit": 5})
        assert response.json["refreshed"] == 1
        assert seen == {"urls": ["https://github.com/a/b"], "limit": 5}
        session.commit.assert_called_once()

    def test_defaults(self, monkeypatch):
        _, seen, _ = self._call(monkeypatch, {})
        assert seen["limit"] == svc.DEFAULT_REFRESH_LIMIT

    @pytest.mark.parametrize("body", [{"limit": 0}, {"limit": 1000}, {"limit": "x"}, {"status": "nope"}])
    def test_rejects_bad_input(self, monkeypatch, body):
        from werkzeug.exceptions import BadRequest

        with pytest.raises(BadRequest):
            self._call(monkeypatch, body)

    def _call_one(self, monkeypatch, body, item):
        from library.tool_recommendation_routes import refresh_github_stats

        session = MagicMock()
        session.get.return_value = item
        monkeypatch.setattr("library.tool_recommendation_routes.get_scoped_session", lambda: session)
        seen = {}

        def fake_refresh(sess, urls, limit, force=False):
            seen.update(urls=list(urls), limit=limit, force=force)
            return {"repositories": 1, "refreshed": 1, "failed": 0, "rate_limited": False, "pending": 0}

        monkeypatch.setattr(svc, "refresh_stale", fake_refresh)
        with Flask(__name__).test_request_context("/x", method="POST", json=body):
            g.auth = SimpleNamespace(kind="user", user_id=1)
            response = refresh_github_stats()
        return response, seen, session

    def test_force_refreshes_one_entry_whatever_its_age(self, monkeypatch):
        item = SimpleNamespace(homepage_url="https://github.com/anchore/grype", links=[])
        response, seen, session = self._call_one(monkeypatch, {"id": 778, "force": True}, item)
        assert response.json["refreshed"] == 1
        assert seen == {"urls": ["https://github.com/anchore/grype"], "limit": 1, "force": True}
        session.commit.assert_called_once()

    def test_single_entry_without_force_keeps_the_freshness_rule(self, monkeypatch):
        item = SimpleNamespace(homepage_url="https://github.com/anchore/grype", links=[])
        _, seen, _ = self._call_one(monkeypatch, {"id": 778}, item)
        assert seen["force"] is False

    @pytest.mark.parametrize("body, item", [
        ({"id": 1, "force": True}, SimpleNamespace(homepage_url="https://example.com/tool", links=[])),
        ({"id": 1, "force": "yes"}, SimpleNamespace(homepage_url="https://github.com/a/b", links=[])),
        ({"id": "x"}, SimpleNamespace(homepage_url="https://github.com/a/b", links=[])),
    ])
    def test_single_entry_rejects_bad_input(self, monkeypatch, body, item):
        from werkzeug.exceptions import BadRequest

        with pytest.raises(BadRequest):
            self._call_one(monkeypatch, body, item)

    def test_unknown_entry_is_404(self, monkeypatch):
        from werkzeug.exceptions import NotFound

        with pytest.raises(NotFound):
            self._call_one(monkeypatch, {"id": 1}, None)

    def test_bulk_force_is_refused(self, monkeypatch):
        from werkzeug.exceptions import BadRequest

        with pytest.raises(BadRequest):
            self._call(monkeypatch, {"force": True})

    def test_service_key_is_allowed_like_every_radar_write(self, monkeypatch):
        response, _, _ = self._call(monkeypatch, {}, kind="service")
        assert response.json["refreshed"] == 1

    def test_rate_endpoint_returns_the_quota(self, monkeypatch):
        from library.tool_recommendation_routes import get_github_rate

        quota = {"limit": 5000, "remaining": 5000, "reset": "2026-10-23T17:53:50+00:00", "authenticated": True}
        monkeypatch.setattr(svc, "fetch_rate_limit", lambda: quota)
        with Flask(__name__).test_request_context("/tool_recommendations/github_rate"):
            g.auth = SimpleNamespace(kind="user", user_id=1)
            assert get_github_rate().json == {"rate": quota}

    def test_rate_endpoint_when_github_is_unreachable(self, monkeypatch):
        from library.tool_recommendation_routes import get_github_rate

        monkeypatch.setattr(svc, "fetch_rate_limit", lambda: None)
        with Flask(__name__).test_request_context("/tool_recommendations/github_rate"):
            g.auth = SimpleNamespace(kind="user", user_id=1)
            assert get_github_rate().json == {"rate": None}

    def test_unknown_key_kind_is_refused(self, monkeypatch):
        from werkzeug.exceptions import Forbidden

        with pytest.raises(Forbidden):
            self._call(monkeypatch, {}, kind="anonymous")


class TestParseRepositoryUrl:
    @pytest.mark.parametrize("url, provider, key, path", [
        ("https://github.com/GaiaNet-AI/gaianet-node", "github", "gaianet-ai/gaianet-node", "GaiaNet-AI/gaianet-node"),
        ("https://gitlab.com/gitlab-org/gitlab", "gitlab", "gitlab.com/gitlab-org/gitlab", "gitlab-org/gitlab"),
        ("https://gitlab.tt-rss.org/tt-rss/tt-rss", "gitlab", "gitlab.tt-rss.org/tt-rss/tt-rss", "tt-rss/tt-rss"),
        ("https://gitlab.tt-rss.org/tt-rss/tt-rss/-/tree/master/docs", "gitlab", "gitlab.tt-rss.org/tt-rss/tt-rss", "tt-rss/tt-rss"),
        ("gitlab.com/group/sub/project.git", "gitlab", "gitlab.com/group/sub/project", "group/sub/project"),
        ("  HTTPS://GitLab.com/Group/Project/ ", "gitlab", "gitlab.com/group/project", "Group/Project"),
    ])
    def test_repositories(self, url, provider, key, path):
        ref = svc.parse_repository_url(url)
        assert (ref.provider, ref.key, ref.path) == (provider, key, path)

    def test_gitlab_ref_splits_owner_and_repo(self):
        ref = svc.parse_repository_url("https://gitlab.com/group/sub/project")
        assert (ref.host, ref.owner, ref.repo, ref.url) == ("gitlab.com", "group/sub", "project", "https://gitlab.com/group/sub/project")

    @pytest.mark.parametrize("url", [
        None, "", "https://example.com/a/b", "https://notgitlab.com/a/b", "https://gitlab.com/a", "https://gitlab.com/",
        "https://gitlab.com/explore/projects", "https://gitlab.com/users/someone", "https://gitlab.com/-/profile/x",
        "https://gitlab/a/b", "ftp://gitlab.com/a/b", "https://gitlab.com/a b/c",
    ])
    def test_not_a_repository(self, url):
        assert svc.parse_repository_url(url) is None

    def test_repository_urls_flattens_and_dedupes(self):
        links = [{"url": "https://docs.example.com", "label": "Docs"}, {"url": "https://github.com/a/b"}, "bad", {"label": "x"}]
        result = svc.repository_urls(" https://github.com/a/b ", None, links, "")
        assert result == ["https://github.com/a/b", "https://docs.example.com", "bad"]


class TestFetchGitlabRepo:
    def _patch(self, monkeypatch, status, payload=None):
        seen = {}
        response = SimpleNamespace(status_code=status, headers={}, ok=200 <= status < 400, json=lambda: payload)

        def fake(*, service, operation, request_fn, success_fn=None):
            seen["service"] = service
            seen["success"] = success_fn(response)
            return response

        monkeypatch.setattr(svc, "_assert_public_host", lambda host: None)
        monkeypatch.setattr(svc, "observed_request", fake)
        return seen

    def test_ok(self, monkeypatch):
        seen = self._patch(monkeypatch, 200, {"star_count": 3})
        assert svc.fetch_gitlab_repo("gitlab.com", "a/b") == {"star_count": 3}
        assert seen == {"service": "gitlab", "success": True}

    @pytest.mark.parametrize("status", [404, 301, 302])
    def test_missing_or_moved_project_has_no_numbers(self, monkeypatch, status):
        # gitlab.tt-rss.org answers 301 to github.com/tt-rss: the numbers live at the other address
        self._patch(monkeypatch, status)
        assert svc.fetch_gitlab_repo("gitlab.tt-rss.org", "tt-rss/tt-rss") is None

    def test_rate_limit(self, monkeypatch):
        self._patch(monkeypatch, 429)
        with pytest.raises(svc.GithubRateLimited):
            svc.fetch_gitlab_repo("gitlab.com", "a/b")

    def test_server_error(self, monkeypatch):
        self._patch(monkeypatch, 500)
        with pytest.raises(svc.GithubError):
            svc.fetch_gitlab_repo("gitlab.com", "a/b")

    def test_private_address_is_refused(self, monkeypatch):
        monkeypatch.setattr(svc.socket, "getaddrinfo", lambda *a, **k: [(2, 1, 6, "", ("127.0.0.1", 443))])
        with pytest.raises(svc.GithubError):
            svc.fetch_gitlab_repo("gitlab.internal.example", "a/b")

    def test_unresolvable_host_is_an_error(self, monkeypatch):
        def boom(*args, **kwargs):
            raise OSError("no such host")

        monkeypatch.setattr(svc.socket, "getaddrinfo", boom)
        with pytest.raises(svc.GithubError):
            svc.fetch_gitlab_repo("gitlab.gone.example", "a/b")


GITLAB_JSON = {
    "path": "tt-rss", "namespace": {"full_path": "tt-rss"}, "description": "Feed reader", "star_count": 120,
    "forks_count": 15, "open_issues_count": 9, "archived": False, "topics": ["rss", 5], "created_at": "2013-01-02T03:04:05.000Z",
    "last_activity_at": "2026-10-20T10:00:00.123Z", "license": {"key": "gpl-3.0", "nickname": "GNU GPLv3"},
}


class TestRefreshGitlabRepo:
    def test_maps_gitlab_fields_onto_a_new_row(self, monkeypatch):
        monkeypatch.setattr(svc, "fetch_gitlab_repo", lambda host, path: GITLAB_JSON)
        session = MagicMock()
        session.execute.return_value.scalars.return_value.first.return_value = None

        row = svc.refresh_gitlab_repo(session, "gitlab.tt-rss.org", "tt-rss/tt-rss", now=NOW)

        session.add.assert_called_once_with(row)
        assert (row.full_name_key, row.provider, row.host) == ("gitlab.tt-rss.org/tt-rss/tt-rss", "gitlab", "gitlab.tt-rss.org")
        assert (row.owner, row.repo) == ("tt-rss", "tt-rss")
        assert (row.stars, row.forks, row.watchers, row.open_issues) == (120, 15, None, 9)
        assert (row.license, row.topics, row.archived, row.status) == ("GNU GPLv3", ["rss"], False, "ok")
        assert row.pushed_at == dt.datetime(2026, 10, 20, 10, 0, 0, 123000, tzinfo=dt.timezone.utc)

    def test_not_found_keeps_the_last_known_numbers(self, monkeypatch):
        monkeypatch.setattr(svc, "fetch_gitlab_repo", lambda host, path: None)
        existing = SimpleNamespace(stars=10, status="ok", fetched_at=None)
        session = MagicMock()
        session.execute.return_value.scalars.return_value.first.return_value = existing

        row = svc.refresh_gitlab_repo(session, "gitlab.com", "a/b", now=NOW)

        assert (row.status, row.stars, row.fetched_at) == ("not_found", 10, NOW)


class TestRefreshStaleMixedProviders:
    def test_each_provider_uses_its_own_refresher(self, monkeypatch):
        calls = []
        monkeypatch.setattr(svc, "refresh_repo", lambda session, owner, repo, now=None: calls.append(("github", owner, repo)))
        monkeypatch.setattr(svc, "refresh_gitlab_repo", lambda session, host, path, now=None: calls.append(("gitlab", host, path)))
        session = MagicMock()
        session.execute.return_value.scalars.return_value.all.return_value = []

        summary = svc.refresh_stale(
            session, ["https://github.com/tt-rss/tt-rss", "https://gitlab.tt-rss.org/tt-rss/tt-rss", "https://tt-rss.org"],
            limit=10, now=NOW,
        )

        assert calls == [("github", "tt-rss", "tt-rss"), ("gitlab", "gitlab.tt-rss.org", "tt-rss/tt-rss")]
        assert summary["repositories"] == 2 and summary["refreshed"] == 2

    def test_gitlab_rate_limit_stops_the_run(self, monkeypatch):
        def limited(session, host, path, now=None):
            raise svc.GithubRateLimited("slow down")

        monkeypatch.setattr(svc, "refresh_gitlab_repo", limited)
        session = MagicMock()
        session.execute.return_value.scalars.return_value.all.return_value = []

        summary = svc.refresh_stale(session, ["https://gitlab.com/a/b", "https://gitlab.com/a/c"], now=NOW)

        assert summary["rate_limited"] is True and summary["pending"] == 2


def _row(key, provider="github", host="github.com", owner="o", repo="r", **kwargs):
    values = dict(
        full_name_key=key, provider=provider, host=host, owner=owner, repo=repo, status="ok", stars=None, forks=None,
        watchers=None, open_issues=None, language=None, license=None, archived=False, pushed_at=None, fetched_at=NOW,
        description=None, topics=[],
    )
    values.update(kwargs)
    return SimpleNamespace(**values)


class TestCombinedStats:
    def _session(self, rows):
        session = MagicMock()
        session.execute.return_value.scalars.return_value.all.return_value = rows
        return session

    def test_sums_repositories_and_keeps_the_breakdown(self):
        github = _row("tt-rss/tt-rss", owner="tt-rss", repo="tt-rss", stars=868, forks=88, watchers=40, open_issues=5,
                      language="PHP", license="GPL-3.0", pushed_at=NOW, topics=["rss"], description="Feed reader")
        gitlab = _row("gitlab.example.org/tt/mirror", provider="gitlab", host="gitlab.example.org", owner="tt", repo="mirror",
                      stars=12, forks=2, open_issues=1, fetched_at=NOW - dt.timedelta(days=2), topics=["rss", "php"],
                      pushed_at=NOW - dt.timedelta(days=1))
        entries = {576: ["https://github.com/tt-rss/tt-rss", "https://gitlab.example.org/tt/mirror", "https://tt-rss.org"]}

        result = svc.combined_stats_for_entries(self._session([github, gitlab]), entries)[576]

        assert (result["stars"], result["forks"], result["watchers"], result["open_issues"]) == (880, 90, 40, 6)
        assert (result["full_name"], result["language"], result["license"]) == ("tt-rss/tt-rss", "PHP", "GPL-3.0")
        assert result["topics"] == ["rss", "php"] and result["archived"] is False
        assert result["pushed_at"] == NOW.isoformat()
        assert result["fetched_at"] == (NOW - dt.timedelta(days=2)).isoformat()  # the oldest row decides staleness
        assert [r["provider"] for r in result["repositories"]] == ["github", "gitlab"]
        assert result["repositories"][1]["full_name"] == "gitlab.example.org/tt/mirror"

    def test_a_moved_gitlab_project_without_numbers_adds_nothing(self):
        github = _row("tt-rss/tt-rss", owner="tt-rss", repo="tt-rss", stars=868, forks=88)
        moved = _row("gitlab.tt-rss.org/tt-rss/tt-rss", provider="gitlab", host="gitlab.tt-rss.org", owner="tt-rss",
                     repo="tt-rss", status="not_found")
        entries = {1: ["https://gitlab.tt-rss.org/tt-rss/tt-rss", "https://github.com/tt-rss/tt-rss"]}

        result = svc.combined_stats_for_entries(self._session([github, moved]), entries)[1]

        assert (result["stars"], result["forks"], result["status"]) == (868, 88, "ok")
        assert result["watchers"] is None and len(result["repositories"]) == 2

    def test_same_repository_named_twice_counts_once(self):
        row = _row("a/b", owner="a", repo="b", stars=5)
        entries = {1: ["https://github.com/a/b", "https://github.com/A/B/", "github.com/a/b.git"]}

        result = svc.combined_stats_for_entries(self._session([row]), entries)[1]

        assert result["stars"] == 5 and len(result["repositories"]) == 1

    def test_archived_only_when_every_repository_is(self):
        first = _row("a/b", owner="a", repo="b", archived=True)
        second = _row("a/c", owner="a", repo="c", archived=False)
        both = svc.combined_stats_for_entries(self._session([first, second]), {1: ["https://github.com/a/b", "https://github.com/a/c"]})
        assert both[1]["archived"] is False
        only = svc.combined_stats_for_entries(self._session([first]), {1: ["https://github.com/a/b"]})
        assert only[1]["archived"] is True

    def test_entries_without_stored_rows_or_repositories_are_absent(self):
        entries = {1: ["https://github.com/a/never-fetched"], 2: ["https://example.com"], 3: []}
        assert svc.combined_stats_for_entries(self._session([]), entries) == {}

    def test_no_repository_urls_means_no_query(self):
        session = MagicMock()
        assert svc.combined_stats_for_entries(session, {1: ["https://example.com"]}) == {}
        session.execute.assert_not_called()
