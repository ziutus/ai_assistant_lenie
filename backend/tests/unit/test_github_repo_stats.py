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
        session.execute.return_value.scalars.return_value.all.return_value = ["https://github.com/a/b"]
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

    def test_service_key_is_refused(self, monkeypatch):
        from werkzeug.exceptions import Forbidden

        with pytest.raises(Forbidden):
            self._call(monkeypatch, {}, kind="service")
