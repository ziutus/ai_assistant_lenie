"""Tests for project cards: import normalization, validation, age filter and REST contract."""

from unittest.mock import MagicMock, patch

import flask
import pytest

pytest.importorskip("sqlalchemy")

import library.project_card_routes as routes
from library.db.models import ProjectCard
from library.project_cards import (
    ProjectCardError,
    age_fit,
    card_to_dict,
    group_label,
    normalize_import_card,
    upsert_cards,
    validate_fields,
)


def _raw(**overrides):
    raw = {
        "number": "001",
        "file": "001 - Magiczna Waga z Kartonu.pdf",
        "flags": [],
        "group_raw": "DŹWIGNIEIKOŁYSKI",
        "title": "Magiczna Waga z Kartonu",
        "age_min": 5,
        "age_max": 9,
        "time_min": 30,
        "time_max": 30,
        "difficulty": 1,
        "needs_adult": True,
        "materials": [{"qty": "1", "name": "Taśma klejąca"}],
        "tools": ["nożyczki"],
        "steps": ["Zrób dwa otwory."],
        "troubleshooting": [{"problem": "Nie działa", "solution": "Sprawdź."}],
        "variants": ["Udekoruj wagę."],
        "safety": "Potrzebny dorosły.",
    }
    raw.update(overrides)
    return raw


def _card(**overrides):
    values = {"id": 1, "series": "S", "number": 1, "title": "T", "age_min": 6, "age_max": 10,
              "review_status": "imported"}
    values.update(overrides)
    return ProjectCard(**values)


@pytest.fixture()
def client():
    app = flask.Flask(__name__)
    app.register_blueprint(routes.bp)
    app.config["TESTING"] = True
    return app.test_client()


def test_normalize_import_card_maps_group_and_number():
    card = normalize_import_card(_raw())
    assert card["number"] == 1
    assert card["series"] == "Niesamowite Maszyny"
    assert card["group_name"] == "Dźwignie i kołyski"
    assert card["review_status"] == "imported"
    assert card["source_file"].startswith("001 - ")


def test_normalize_import_card_flags_mark_needs_review():
    card = normalize_import_card(_raw(flags=["step_uses_unlisted:silnik"]))
    assert card["review_status"] == "needs_review"
    assert card["import_flags"] == ["step_uses_unlisted:silnik"]


def test_normalize_import_card_keeps_reviewed_status_and_extra_fields():
    card = normalize_import_card(_raw(review_status="reviewed", what_child_does=["Wkłada przedmioty"]))
    assert card["review_status"] == "reviewed"
    assert card["what_child_does"] == ["Wkłada przedmioty"]


@pytest.mark.parametrize("bad", [{"number": "x"}, {"title": ""}, {"age_min": 12, "age_max": 5}, {"difficulty": 4}])
def test_normalize_import_card_rejects_invalid(bad):
    with pytest.raises(ProjectCardError):
        normalize_import_card(_raw(**bad))


def test_validate_fields_rejects_unknown_and_wrong_types():
    with pytest.raises(ProjectCardError):
        validate_fields({"id": 5})
    with pytest.raises(ProjectCardError):
        validate_fields({"needs_adult": "yes"})
    with pytest.raises(ProjectCardError):
        validate_fields({"tools": "nożyczki"})
    with pytest.raises(ProjectCardError):
        validate_fields({"review_status": "done"})
    with pytest.raises(ProjectCardError):
        validate_fields({"materials": [{"qty": "1"}]})


def test_age_fit_ok_stretch_and_none():
    card = _card(age_min=6, age_max=10)
    assert age_fit(card, 7) == "ok"
    assert age_fit(card, 5) is None
    assert age_fit(card, 5, stretch=1) == "stretch"
    assert age_fit(card, 4, stretch=1) is None
    assert age_fit(_card(age_min=None, age_max=None), 5) == "unknown"


def test_group_label_known_and_unknown():
    assert group_label("BLOCZKIIDŹWIGI") == "Bloczki i dźwigi"
    assert group_label("COŚ NOWEGO") == "COŚ NOWEGO"
    assert group_label(None) is None


def test_card_to_dict_summary_vs_detail():
    card = _card(steps=["a"], materials=[])
    assert "steps" not in card_to_dict(card)
    assert card_to_dict(card, detail=True)["steps"] == ["a"]
    assert card_to_dict(card, age=7)["age_fit"] == "ok"


def _session_returning(existing):
    session = MagicMock()
    session.execute.return_value.scalar_one_or_none.return_value = existing
    return session


def test_upsert_creates_new_card():
    session = _session_returning(None)
    result = upsert_cards(session, [_raw()])
    assert result.as_dict() == {"created": 1, "updated": 0, "kept_reviewed": 0}
    added = session.add.call_args[0][0]
    assert added.title == "Magiczna Waga z Kartonu"
    session.commit.assert_called_once()


def test_upsert_does_not_overwrite_reviewed_card_with_unreviewed_import():
    existing = _card(title="Poprawiony tytuł", review_status="reviewed")
    result = upsert_cards(_session_returning(existing), [_raw()])
    assert result.kept_reviewed == 1
    assert existing.title == "Poprawiony tytuł"


def test_upsert_reviewed_import_replaces_reviewed_card():
    existing = _card(title="Stary", review_status="reviewed")
    result = upsert_cards(_session_returning(existing), [_raw(review_status="reviewed")])
    assert result.updated == 1
    assert existing.title == "Magiczna Waga z Kartonu"


def test_get_list_passes_filters_and_returns_age_fit(client):
    session = MagicMock()
    with patch.object(routes, "get_scoped_session", return_value=session), \
            patch.object(routes, "list_cards", return_value=([_card()], 61)) as list_cards, \
            patch.object(routes, "group_counts", return_value=[{"name": "G", "count": 1}]):
        response = client.get("/project_cards?age=7&stretch=1&max_difficulty=2&needs_adult=true&q=waga&limit=25&offset=50")
    body = response.get_json()
    assert response.status_code == 200
    assert body["cards"][0]["age_fit"] == "ok"
    assert body["groups"] == [{"name": "G", "count": 1}]
    assert body["total"] == 61 and body["limit"] == 25 and body["offset"] == 50
    kwargs = list_cards.call_args.kwargs
    assert kwargs["age"] == 7 and kwargs["stretch"] == 1 and kwargs["max_difficulty"] == 2
    assert kwargs["needs_adult"] is True and kwargs["query"] == "waga"
    assert kwargs["limit"] == 25 and kwargs["offset"] == 50


@pytest.mark.parametrize("query", ["age=abc", "age=40", "max_difficulty=9", "review_status=nope", "needs_adult=maybe", "limit=0", "limit=500"])
def test_get_list_rejects_bad_params(client, query):
    with patch.object(routes, "get_scoped_session", return_value=MagicMock()):
        response = client.get(f"/project_cards?{query}")
    assert response.status_code == 400


def test_get_card_404_and_detail(client):
    session = MagicMock()
    session.get.return_value = None
    with patch.object(routes, "get_scoped_session", return_value=session):
        assert client.get("/project_cards/9").status_code == 404
    session.get.return_value = _card(steps=["x"])
    with patch.object(routes, "get_scoped_session", return_value=session):
        response = client.get("/project_cards/1")
    assert response.get_json()["card"]["steps"] == ["x"]


def test_patch_updates_and_validates(client):
    session = MagicMock()
    card = _card()
    session.get.return_value = card
    with patch.object(routes, "get_scoped_session", return_value=session):
        ok = client.patch("/project_cards/1", json={"review_status": "reviewed", "age_min": 5})
        bad = client.patch("/project_cards/1", json={"age_min": 99})
        empty = client.patch("/project_cards/1", json={})
    assert ok.status_code == 200
    assert card.review_status == "reviewed" and card.age_min == 5
    assert bad.status_code == 400
    assert empty.status_code == 400


def test_import_endpoint(client):
    session = MagicMock()
    with patch.object(routes, "get_scoped_session", return_value=session):
        with patch.object(routes, "upsert_cards") as upsert:
            upsert.return_value.as_dict.return_value = {"created": 2, "updated": 0, "kept_reviewed": 0}
            response = client.post("/project_cards/import", json={"cards": [_raw(), _raw(number="002")]})
        missing = client.post("/project_cards/import", json={"cards": []})
        broken = client.post("/project_cards/import", json={"cards": "x"})
    assert response.get_json()["created"] == 2
    assert missing.status_code == 400 and broken.status_code == 400


_SVG = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 10 10"><rect width="10" height="10" font-size="3"/></svg>'


def test_illustration_svg_accepts_plain_svg_and_clears_on_empty():
    assert validate_fields({"illustration_svg": f"  {_SVG}\n"})["illustration_svg"] == _SVG
    assert validate_fields({"illustration_svg": ""})["illustration_svg"] is None
    assert validate_fields({"illustration_svg": None})["illustration_svg"] is None


@pytest.mark.parametrize("bad", [
    "<p>nie svg</p>",
    '<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>',
    '<svg xmlns="http://www.w3.org/2000/svg" onload="x()"></svg>',
    '<svg xmlns="http://www.w3.org/2000/svg"><a href="https://evil.test"><rect/></a></svg>',
    '<svg xmlns="http://www.w3.org/2000/svg"><foreignObject/></svg>',
    '<svg xmlns="http://www.w3.org/2000/svg"><style>@import url(x)</style></svg>',
    '<!DOCTYPE svg><svg xmlns="http://www.w3.org/2000/svg"></svg>',
    "<svg>niedomknięte",
    123,
])
def test_illustration_svg_rejects_active_or_malformed_content(bad):
    with pytest.raises(ProjectCardError):
        validate_fields({"illustration_svg": bad})


def test_source_pdf_key_is_stable_and_ascii():
    from library.project_cards import source_pdf_key

    assert source_pdf_key("Niesamowite Maszyny", 1) == "project_cards/niesamowite-maszyny/001.pdf"
    assert source_pdf_key("Łódź & Co", 56) == "project_cards/lodz-co/056.pdf"


@pytest.mark.parametrize("data", [b"", b"nie pdf", b"<html>%PDF-</html>"])
def test_validate_pdf_rejects_non_pdf(data):
    from library.project_cards import validate_pdf

    with pytest.raises(ProjectCardError):
        validate_pdf(data)


class _FakeStorage:
    def __init__(self, url="https://minio.test/signed"):
        self.objects, self.url = {}, url

    def put_bytes(self, key, data, content_type=None):
        self.objects[key] = (data, content_type)

    def get_bytes(self, key):
        return self.objects[key][0]

    def presigned_get_url(self, key, expires_in=3600):
        return self.url


def _post_pdf(client, session, storage, content=b"%PDF-1.4 test", name="001 - Waga.pdf", field="file"):
    import io

    with patch.object(routes, "get_scoped_session", return_value=session), \
            patch.object(routes, "_storage", return_value=storage):
        return client.post("/project_cards/1/source_pdf", data={field: (io.BytesIO(content), name)},
                           content_type="multipart/form-data")


def test_upload_source_pdf_stores_file_and_sets_key(client):
    card = _card(series="Niesamowite Maszyny", number=1, source_file=None)
    session, storage = MagicMock(), _FakeStorage()
    session.get.return_value = card
    response = _post_pdf(client, session, storage)
    assert response.status_code == 200 and response.get_json()["bytes"] == len(b"%PDF-1.4 test")
    assert storage.objects["project_cards/niesamowite-maszyny/001.pdf"] == (b"%PDF-1.4 test", "application/pdf")
    assert card.source_pdf_key == "project_cards/niesamowite-maszyny/001.pdf"
    assert card.source_file == "001 - Waga.pdf"
    session.commit.assert_called_once()


def test_upload_source_pdf_rejects_bad_input(client):
    session = MagicMock()
    session.get.return_value = _card()
    assert _post_pdf(client, session, _FakeStorage(), content=b"GIF89a").status_code == 400
    assert _post_pdf(client, session, _FakeStorage(), field="other").status_code == 400
    session.get.return_value = None
    assert _post_pdf(client, session, _FakeStorage()).status_code == 404


def test_get_source_pdf_returns_presigned_url_or_bytes(client):
    session = MagicMock()
    storage = _FakeStorage()
    storage.objects["k"] = (b"%PDF-1.4 x", "application/pdf")
    session.get.return_value = _card(source_pdf_key="k", number=1)
    with patch.object(routes, "get_scoped_session", return_value=session), \
            patch.object(routes, "_storage", return_value=storage):
        link = client.get("/project_cards/1/source_pdf")
        download = client.get("/project_cards/1/source_pdf?download=1")
        session.get.return_value = _card(source_pdf_key=None)
        missing = client.get("/project_cards/1/source_pdf")
    assert link.get_json()["url"] == "https://minio.test/signed"
    assert download.data == b"%PDF-1.4 x" and download.mimetype == "application/pdf"
    assert missing.status_code == 404


def test_has_source_pdf_flag():
    assert card_to_dict(_card(source_pdf_key="k"))["has_source_pdf"] is True
    assert card_to_dict(_card(), detail=True)["has_source_pdf"] is False


def _section(**overrides):
    section = {"role": "explanation", "title": "Dlaczego to działa", "format": "text", "content": "Gęstość.",
               "hidden": False}
    section.update(overrides)
    return section


def test_sections_are_validated_and_unknown_roles_become_other():
    cleaned = validate_fields({"sections": [
        _section(),
        _section(role="solution", format="steps", content=["Krok", " Drugi "], hidden=True),
        _section(role="coś nowego", title="Inne"),
    ]})["sections"]
    assert cleaned[1]["content"] == ["Krok", "Drugi"] and cleaned[1]["hidden"] is True
    assert cleaned[2]["role"] == "other"
    assert validate_fields({"sections": None})["sections"] == []


@pytest.mark.parametrize("bad", [
    "nie lista",
    [{"title": ""}],
    [_section(format="html")],
    [_section(hidden="tak")],
    [_section(format="list", content="to nie lista")],
    [_section(content="x" * 20_001)],
    [_section()] * 31,
    ["nie obiekt"],
])
def test_sections_reject_malformed_input(bad):
    with pytest.raises(ProjectCardError):
        validate_fields({"sections": bad})


def test_kind_is_validated():
    assert validate_fields({"kind": "puzzle"})["kind"] == "puzzle"
    with pytest.raises(ProjectCardError):
        validate_fields({"kind": "game"})


def test_normalize_import_card_for_card_book_family():
    card = normalize_import_card({
        "number": "007", "title": "Magia Pływającego Jajka", "series": "Domowe Eksperymenty Naukowe",
        "kind": "experiment", "chapter": "Woda i ciecze", "age_min": 6, "age_max": 12, "age_source": "cover",
        "time_min": 3, "time_max": 3, "source_file": "pl_200.pdf", "source_page": 9, "flags": [],
        "sections": [_section()], "time_raw": "3 MIN",
    })
    assert card["kind"] == "experiment" and card["group_name"] == "Woda i ciecze"
    assert card["source_file"] == "pl_200.pdf" and card["source_page"] == 9 and card["number"] == 7
    assert card["import_flags"] == ["age_from_cover"] and card["review_status"] == "imported"
    assert card["sections"][0]["role"] == "explanation"


def test_normalize_import_card_defaults_kind_to_project():
    assert normalize_import_card(_raw())["kind"] == "project"


def test_card_to_dict_exposes_kind_sections_and_page():
    card = _card(kind="puzzle", sections=[_section()], source_page=12)
    assert card_to_dict(card)["kind"] == "puzzle" and card_to_dict(card)["source_page"] == 12
    assert "sections" not in card_to_dict(card)
    assert card_to_dict(card, detail=True)["sections"][0]["title"] == "Dlaczego to działa"


def test_list_filters_by_kind_and_series_and_returns_facets(client):
    with patch.object(routes, "get_scoped_session", return_value=MagicMock()), \
            patch.object(routes, "list_cards", return_value=([_card()], 1)) as list_cards, \
            patch.object(routes, "group_counts", return_value=[]), \
            patch.object(routes, "series_counts", return_value=[{"name": "S", "kind": "puzzle", "count": 1}]):
        response = client.get("/project_cards?kind=puzzle&series=S")
        bad = client.get("/project_cards?kind=game")
    body = response.get_json()
    assert list_cards.call_args.kwargs["kind"] == "puzzle" and list_cards.call_args.kwargs["series"] == "S"
    assert body["series"][0]["kind"] == "puzzle" and "puzzle" in body["kinds"]
    assert bad.status_code == 400


def test_series_pdf_key():
    from library.project_cards import series_pdf_key

    assert series_pdf_key("Laboratorium Logiki") == "project_cards/laboratorium-logiki/book.pdf"


def _post_series_pdf(client, session, storage, *, series="Laboratorium Logiki", content=b"%PDF-1.7 book"):
    import io

    data = {"file": (io.BytesIO(content), "book.pdf")}
    if series is not None:
        data["series"] = series
    with patch.object(routes, "get_scoped_session", return_value=session), \
            patch.object(routes, "_storage", return_value=storage):
        return client.post("/project_cards/series_pdf", data=data, content_type="multipart/form-data")


def test_series_pdf_is_stored_once_and_linked_to_every_card(client):
    cards = [_card(id=1, number=1), _card(id=2, number=2)]
    session, storage = MagicMock(), _FakeStorage()
    session.query.return_value.filter.return_value.all.return_value = cards
    response = _post_series_pdf(client, session, storage)
    assert response.get_json()["cards"] == 2
    assert list(storage.objects) == ["project_cards/laboratorium-logiki/book.pdf"]
    assert all(card.source_pdf_key == "project_cards/laboratorium-logiki/book.pdf" for card in cards)
    session.commit.assert_called_once()


def test_series_pdf_rejects_bad_requests(client):
    session = MagicMock()
    session.query.return_value.filter.return_value.all.return_value = []
    assert _post_series_pdf(client, session, _FakeStorage(), series=None).status_code == 400
    assert _post_series_pdf(client, session, _FakeStorage(), content=b"GIF89a").status_code == 400
    assert _post_series_pdf(client, session, _FakeStorage()).status_code == 404


def test_source_pdf_link_opens_the_card_page_for_series_pdfs(client):
    session, storage = MagicMock(), _FakeStorage()
    session.get.return_value = _card(source_pdf_key="project_cards/s/book.pdf", source_page=42)
    with patch.object(routes, "get_scoped_session", return_value=session), \
            patch.object(routes, "_storage", return_value=storage):
        book = client.get("/project_cards/1/source_pdf").get_json()["url"]
        session.get.return_value = _card(source_pdf_key="project_cards/s/001.pdf", source_page=42)
        single = client.get("/project_cards/1/source_pdf").get_json()["url"]
    assert book == "https://minio.test/signed#page=42" and single == "https://minio.test/signed"


def test_illustration_svg_rejects_oversized_document():
    with pytest.raises(ProjectCardError, match="larger"):
        validate_fields({"illustration_svg": "<svg>" + "x" * 100_001 + "</svg>"})


def test_illustration_svg_in_detail_only_and_flag_in_summary():
    card = _card(illustration_svg=_SVG)
    assert card_to_dict(card)["has_illustration"] is True
    assert "illustration_svg" not in card_to_dict(card)
    assert card_to_dict(card, detail=True)["illustration_svg"] == _SVG
    assert card_to_dict(_card())["has_illustration"] is False
