"""Place registry: Wikipedia URL validation, profile upsert/alias matching and the /places endpoints."""

from unittest.mock import MagicMock, patch

import pytest

pytest.importorskip("sqlalchemy")

from library.db.models import PlaceProfile  # noqa: E402
from library.place_registry import name_key, normalize_wikipedia_url, profile_index, upsert_profile  # noqa: E402

API_HEADERS = {"x-api-key": "test-api-key"}


@pytest.fixture()
def client():
    """Flask test client with auth bypassed (same pattern as test_flask_endpoints_entities)."""
    pytest.importorskip("flask")
    import server
    server.app.config["TESTING"] = True
    with patch.object(server, "check_auth_header"):
        with server.app.test_client() as c:
            yield c


@pytest.mark.parametrize("raw,expected", [
    ("https://en.wikipedia.org/wiki/Yanbu_Commercial_Port", "https://en.wikipedia.org/wiki/Yanbu_Commercial_Port"),
    ("pl.wikipedia.org/wiki/Janbu#Historia", "https://pl.wikipedia.org/wiki/Janbu"),
    ("http://en.m.wikipedia.org/wiki/Yanbu", "https://en.m.wikipedia.org/wiki/Yanbu"),
    ("  ", None),
    (None, None),
])
def test_wikipedia_url_is_normalised(raw, expected):
    assert normalize_wikipedia_url(raw) == expected


@pytest.mark.parametrize("raw", [
    "https://example.com/wiki/Yanbu", "https://evilwikipedia.org/wiki/Yanbu", "https://en.wikipedia.org/",
    "https://en.wikipedia.org/w/index.php?title=Yanbu", "javascript:alert(1)",
])
def test_non_wikipedia_urls_are_rejected(raw):
    with pytest.raises(ValueError):
        normalize_wikipedia_url(raw)


def fake_session(profiles=()):
    session = MagicMock()
    session.scalars.return_value.all.return_value = list(profiles)
    session.scalar.return_value = None
    return session


def test_profile_is_found_by_name_or_alias():
    profile = PlaceProfile(id=1, canonical_name="Yanbu", name_key="yanbu", aliases=["Janbu", "Janubu"])
    index = profile_index(fake_session([profile]))
    assert index["yanbu"] is profile and index[name_key("Janbu")] is profile and index["janubu"] is profile


def test_upsert_creates_a_profile_with_clean_aliases_and_only_written_fields():
    session = fake_session()
    profile = upsert_profile(
        session, " Yanbu ", wikipedia_url="en.wikipedia.org/wiki/Yanbu", aliases=["Janbu", "janbu", "Yanbu", " "],
        set_fields={"wikipedia_url", "aliases"},
    )
    session.add.assert_called_once_with(profile)
    assert (profile.canonical_name, profile.name_key) == ("Yanbu", "yanbu")
    assert profile.wikipedia_url == "https://en.wikipedia.org/wiki/Yanbu"
    assert profile.aliases == ["Janbu"]
    assert profile.note is None


def test_upsert_under_an_alias_edits_the_existing_profile():
    existing = PlaceProfile(id=1, canonical_name="Yanbu", name_key="yanbu", aliases=["Janbu"], note="port")
    session = fake_session([existing])
    profile = upsert_profile(session, "Janbu", wikipedia_url="https://pl.wikipedia.org/wiki/Janbu",
                             set_fields={"wikipedia_url"})
    assert profile is existing
    session.add.assert_not_called()
    assert existing.wikipedia_url == "https://pl.wikipedia.org/wiki/Janbu"
    assert existing.note == "port"


def test_upsert_rejects_too_many_aliases():
    with pytest.raises(ValueError):
        upsert_profile(fake_session(), "Yanbu", aliases=[f"A{i}" for i in range(25)], set_fields={"aliases"})


@pytest.mark.parametrize("body,expected", [
    ({"name": "Yanbu", "wikipedia_url": "https://en.wikipedia.org/wiki/Yanbu"}, 200),
    ({"name": "Yanbu", "wikipedia_url": "https://example.com/x"}, 400),
    ({"wikipedia_url": "https://en.wikipedia.org/wiki/Yanbu"}, 400),
    ({"name": "Yanbu", "aliases": "Janbu"}, 400),
])
def test_profile_endpoint(client, body, expected):
    pytest.importorskip("flask")
    session = fake_session()
    with patch("library.place_routes.get_scoped_session", return_value=session):
        response = client.put("/places/profile", headers=API_HEADERS, json=body)
    assert response.status_code == expected
    if expected == 200:
        assert response.get_json()["profile"]["wikipedia_url"] == "https://en.wikipedia.org/wiki/Yanbu"
        session.commit.assert_called_once()
    else:
        session.commit.assert_not_called()


def test_list_endpoint_validates_paging(client):
    pytest.importorskip("flask")
    with patch("library.place_routes.get_scoped_session", return_value=fake_session()):
        assert client.get("/places?limit=500", headers=API_HEADERS).status_code == 400
        assert client.get("/places/detail", headers=API_HEADERS).status_code == 400
