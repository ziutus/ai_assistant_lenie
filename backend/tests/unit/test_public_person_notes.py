from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

pytest.importorskip("sqlalchemy")

from flask import Flask, g

from library import knowledge_sources
from library.public_person_notes import derive_identity, label_for_url, parse_person_note, role_from_folder


class TestParsePersonNote:
    def test_labelled_urls_prose_and_course_wikilink(self):
        note = (
            "Człowiek legenda zajmujący się Kubernetesem\n"
            "Strona domowa: https://cloudowski.com/\n"
            "newsletter: https://cloudowski.com/newsletter/\n"
            "Autor Kursu: [[Golang For DevOps - Udemy]]\n"
            "https://www.linkedin.com/in/someone/\n"
        )

        parsed = parse_person_note(note)

        assert parsed["description"] == "Człowiek legenda zajmujący się Kubernetesem"
        assert parsed["long_description"] is None
        assert parsed["links"] == [
            {"url": "https://cloudowski.com/", "label": "Strona domowa"},
            {"url": "https://cloudowski.com/newsletter/", "label": "newsletter"},
            {"url": "https://www.linkedin.com/in/someone/", "label": "LinkedIn"},
        ]
        assert parsed["courses"] == [{"title": "Golang For DevOps - Udemy", "role": "instructor"}]

    def test_front_matter_only_note_is_empty(self):
        parsed = parse_person_note("---\ntags:\n  - wiedza/informatyka\n---\n")

        assert parsed == {"description": None, "long_description": None, "links": [], "courses": []}

    def test_several_prose_lines_become_a_long_description(self):
        parsed = parse_person_note("Pierwsza linia.\nDruga linia.\nhttps://lubimyczytac.pl/autor/3709/x\n")

        assert parsed["description"] == "Pierwsza linia."
        assert parsed["long_description"] == "Pierwsza linia.\n\nDruga linia."
        assert parsed["links"][0]["label"] == "Lubimyczytać"

    def test_course_author_without_teaching_words_is_an_author(self):
        parsed = parse_person_note("Autor szkolenia [[Sztuka Notowania - Paweł Kadysz]] na stronie https://pwlk.pl/kursy/x")

        assert parsed["courses"] == [{"title": "Sztuka Notowania - Paweł Kadysz", "role": "instructor"}]
        assert parsed["links"] == [{"url": "https://pwlk.pl/kursy/x", "label": "pwlk.pl"}]

    @pytest.mark.parametrize("url,label", [
        ("https://www.youtube.com/@x", "YouTube"), ("https://youtu.be/abc", "YouTube"), ("https://x.com/a", "X"),
        ("https://pl.wikipedia.org/wiki/A", "Wikipedia"), ("https://example.org/p", "example.org"),
    ])
    def test_labels_from_the_host(self, url, label):
        assert label_for_url(url) == label


class TestDeriveIdentity:
    def test_nickname_and_real_name(self):
        assert derive_identity("Claudowski - Tomasz Cholewa") == {"name": "Tomasz Cholewa", "aliases": ["Claudowski"], "hint": None}

    def test_name_with_a_description_suffix(self):
        identity = derive_identity("Jacek walkiewicz - Mówca motywujący")

        assert identity == {"name": "Jacek Walkiewicz", "aliases": [], "hint": "Mówca motywujący"}

    def test_plain_name(self):
        assert derive_identity("Gynvael Coldwind")["name"] == "Gynvael Coldwind"

    def test_single_word_is_not_a_person(self):
        assert derive_identity("talkpython")["name"] is None


class TestRoleFromFolder:
    def test_only_folders_that_name_a_role_give_one(self):
        assert role_from_folder("podcasterzy") == "podcaster"
        assert role_from_folder("pisarze") == "pisarz"
        assert role_from_folder("IT") is None  # a topic, not a role
        assert role_from_folder("") is None


class TestPersonValidation:
    def test_valid_public_person_fields(self):
        cleaned = knowledge_sources.validate_person_fields({"kind": "public", "role": " podcaster ", "obsidian_note_path": ""})

        assert cleaned == {"kind": "public", "role": "podcaster", "obsidian_note_path": None}

    @pytest.mark.parametrize("data", [{"kind": "vip"}, {"role": "x" * 101}, {"kind": 5}])
    def test_bad_values_are_rejected(self, data):
        with pytest.raises(ValueError):
            knowledge_sources.validate_person_fields(data)

    def test_absent_keys_stay_absent(self):
        assert knowledge_sources.validate_person_fields({}) == {}


class TestSourcePersonRoutes:
    def _call(self, monkeypatch, handler_name, *args, body=None, kind="service", method="POST", person=True, linked=True):
        from library import public_person_routes

        session = MagicMock()
        session.get.side_effect = lambda model, key: (
            SimpleNamespace(id=3, canonical_name="Wojciech Szewko") if model.__name__ == "Person" and key == 3 and person
            else SimpleNamespace(id=26, name="Na Wschód od Bliskiego Wschodu") if model.__name__ == "DiscoverySource" and key == 26
            else None
        )
        monkeypatch.setattr(public_person_routes, "get_scoped_session", lambda: session)
        monkeypatch.setattr(public_person_routes.knowledge_sources, "persons_for_sources",
                            lambda _s: {26: [{"id": 3, "name": "Wojciech Szewko", "role": "host"}]})
        monkeypatch.setattr(public_person_routes.knowledge_sources, "find_person",
                            lambda _s, name: SimpleNamespace(id=3, canonical_name=name) if name == "Szewko" else None)
        monkeypatch.setattr(public_person_routes.knowledge_sources, "link_person", lambda *_a: (SimpleNamespace(), linked))
        monkeypatch.setattr(public_person_routes.knowledge_sources, "unlink_person", lambda *_a: linked)
        app = Flask(__name__)
        with app.test_request_context("/x", method=method, json=body or {}):
            g.auth = SimpleNamespace(kind=kind, user_id=None)
            return getattr(public_person_routes, handler_name)(*args), session

    def test_add_by_id_and_by_name(self, monkeypatch):
        (response, status), session = self._call(monkeypatch, "add_source_person", 26, body={"person_id": 3, "role": "host"})
        assert status == 201 and response.json["persons"][0]["role"] == "host"
        session.commit.assert_called_once()

        (_response, status), _ = self._call(monkeypatch, "add_source_person", 26, body={"name": "Szewko"}, linked=False)
        assert status == 200

    def test_unknown_person_source_or_missing_identifier(self, monkeypatch):
        from werkzeug.exceptions import BadRequest, NotFound

        with pytest.raises(NotFound):
            self._call(monkeypatch, "add_source_person", 26, body={"name": "Nikt"})
        with pytest.raises(NotFound):
            self._call(monkeypatch, "add_source_person", 99, body={"person_id": 3})
        with pytest.raises(BadRequest):
            self._call(monkeypatch, "add_source_person", 26, body={})

    def test_remove_and_unlinked(self, monkeypatch):
        from werkzeug.exceptions import NotFound

        response, _ = self._call(monkeypatch, "remove_source_person", 26, 3, method="DELETE")
        assert response.json["persons"][0]["name"] == "Wojciech Szewko"
        with pytest.raises(NotFound):
            self._call(monkeypatch, "remove_source_person", 26, 3, method="DELETE", linked=False)

    def test_other_key_kinds_are_forbidden(self, monkeypatch):
        with pytest.raises(Exception) as exc_info:
            self._call(monkeypatch, "add_source_person", 26, body={"person_id": 3}, kind="other")
        assert exc_info.value.code == 403


class TestCreatePerson:
    def _call(self, monkeypatch, body, existing=None):
        from library import public_person_routes

        session = MagicMock()
        added = []
        session.add.side_effect = added.append
        monkeypatch.setattr(public_person_routes, "get_scoped_session", lambda: session)
        monkeypatch.setattr(public_person_routes.knowledge_sources, "find_person", lambda _s, _n: existing)
        monkeypatch.setattr(public_person_routes, "_person_dict", lambda _s, person: {"canonical_name": person.canonical_name,
                                                                                      "kind": person.kind, "role": person.role})
        monkeypatch.setattr("library.person_registry.add_person_alias", lambda *_a: True)
        app = Flask(__name__)
        with app.test_request_context("/persons", method="POST", json=body):
            g.auth = SimpleNamespace(kind="user", user_id=1)
            return public_person_routes.create_person(), added, session

    def test_creates_a_public_person(self, monkeypatch):
        (response, status), added, session = self._call(monkeypatch, {
            "canonical_name": " Wojciech Szewko ", "kind": "public", "role": "prowadzący kanał",
            "links": [{"url": "https://www.youtube.com/@NaWschododBliskiegoWschodu", "label": "YouTube"}],
        })

        assert status == 201 and response.json["person"]["kind"] == "public"
        person = added[0]
        assert person.canonical_name == "Wojciech Szewko" and person.role == "prowadzący kanał"
        assert person.links[0]["label"] == "YouTube"
        session.commit.assert_called_once()

    def test_existing_name_is_a_conflict_not_a_duplicate(self, monkeypatch):
        (response, status), added, _ = self._call(
            monkeypatch, {"canonical_name": "Szewko"}, existing=SimpleNamespace(id=7, canonical_name="Wojciech Szewko"),
        )

        assert status == 409 and response.json["existing_person_id"] == 7 and added == []

    def test_name_is_required_and_kind_is_checked(self, monkeypatch):
        from werkzeug.exceptions import BadRequest

        with pytest.raises(BadRequest):
            self._call(monkeypatch, {})
        with pytest.raises(BadRequest):
            self._call(monkeypatch, {"canonical_name": "X Y", "kind": "vip"})
        with pytest.raises(BadRequest):
            self._call(monkeypatch, {"canonical_name": "X Y", "links": [{"url": "ftp://x"}]})
