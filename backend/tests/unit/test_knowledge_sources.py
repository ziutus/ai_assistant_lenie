import datetime as dt
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

pytest.importorskip("sqlalchemy")

from flask import Flask, g

from library import knowledge_sources
from library.tool_note_parser import parse_tool_note


class TestGuessKindAndNames:
    def test_kind_is_guessed_from_the_wording(self):
        assert knowledge_sources.guess_kind("Szkolenie ABCD czyli Automatyzacja Bezpieczeństwa w CICD") == "training"
        assert knowledge_sources.guess_kind("docker swarm Udemy") == "course"
        assert knowledge_sources.guess_kind("AI Devs 3") == "course"
        assert knowledge_sources.guess_kind("wideo.zaufanatrzeciastrona.pl") == "other"

    def test_names_match_ignoring_case_diacritics_and_punctuation(self):
        assert knowledge_sources.normalize_name("Na Wschód od Bliskiego Wschodu") == \
            knowledge_sources.normalize_name("na wschod od bliskiego wschodu!")


class TestValidateFields:
    def test_absent_keys_stay_absent_and_empty_clears(self):
        assert knowledge_sources.validate_fields({}) == {}
        assert knowledge_sources.validate_fields({"kind": "", "rating": None}) == {"kind": None, "rating": None}

    def test_valid_values_are_cleaned(self):
        cleaned = knowledge_sources.validate_fields({
            "kind": "course", "status": "in_progress", "started_on": "2026-09-01", "rating": 4,
            "review_note": "  dobry  ", "url": " https://example.com/kurs ",
        })

        assert cleaned == {
            "kind": "course", "status": "in_progress", "started_on": dt.date(2026, 9, 1), "rating": 4,
            "review_note": "dobry", "url": "https://example.com/kurs",
        }

    @pytest.mark.parametrize("data", [
        {"kind": "blog"}, {"status": "done"}, {"rating": 6}, {"rating": 0}, {"rating": True}, {"rating": "5"},
        {"started_on": "wrzesień"}, {"url": "ftp://x"}, {"review_note": "x" * 5000},
        {"started_on": "2026-02-02", "finished_on": "2026-01-01"},
    ])
    def test_bad_values_are_rejected(self, data):
        with pytest.raises(ValueError):
            knowledge_sources.validate_fields(data)


class TestSourceOfNoteParsing:
    NOTE = """**Purpose:** x
### Key Points:
- a
## Connected notes
## External Links

## Source of note
[[Szkolenie ABCD]]
AI Devs 3: https://example.com/lekcja
https://semgrep.dev/docs/quickstart
brak

creation date: 2024-10-27 05:05
modification date: Sunday 27th October 2024 05:05:02
"""

    def test_wikilinks_labelled_urls_and_bare_urls_are_entries(self):
        sources = parse_tool_note(self.NOTE)["sources"]

        assert sources == [
            {"label": "Szkolenie ABCD", "url": None, "wikilink": True},
            {"label": "AI Devs 3", "url": "https://example.com/lekcja", "wikilink": False},
            {"label": None, "url": "https://semgrep.dev/docs/quickstart", "wikilink": False},
        ]

    def test_empty_section_and_template_dates_give_no_sources(self):
        note = "**Purpose:** x\n## Source of note\n\ncreation date: <% tp.file.creation_date() %>\n"

        assert "sources" not in parse_tool_note(note)

    def test_source_after_connected_notes_is_still_read(self):
        assert parse_tool_note(self.NOTE)["sources"][0]["label"] == "Szkolenie ABCD"


class _Session:
    """Just enough of a session for link_note_sources: sources by name, a link table, flush assigns ids."""

    def __init__(self, sources=()):
        self.sources = list(sources)
        self.links = []
        self.new = []
        self.next_id = 100

    def add(self, row):
        if hasattr(row, "kind") and not hasattr(row, "tool_id"):
            self.sources.append(row)
        else:
            self.links.append(row)

    def flush(self):
        for row in [*self.sources, *self.links]:
            if getattr(row, "id", None) is None:
                row.id = self.next_id
                self.next_id += 1

    def execute(self, _query):
        raise AssertionError("queries are replaced in these tests")


@pytest.fixture
def fake_db(monkeypatch):
    from library.db.models import DiscoverySource, ToolSource

    session = _Session([DiscoverySource(id=5, name="Akademia Bezpiecznego Kodu", kind="course")])
    monkeypatch.setattr(knowledge_sources, "find_source", lambda _s, name: next(
        (src for src in session.sources if knowledge_sources.normalize_name(src.name) == knowledge_sources.normalize_name(name)),
        None,
    ))
    monkeypatch.setattr(knowledge_sources, "note_path_for_title", lambda _s, title: f"02-wiedza/{title}.md")

    def link_tool(_session, tool, source, context=None):
        existing = next((item for item in session.links if item.tool_id == tool.id and item.source_id == source.id), None)
        if existing is not None:
            existing.context = existing.context or context
            return existing, False
        link = ToolSource(tool_id=tool.id, source_id=source.id, context=context)
        session.links.append(link)
        return link, True

    monkeypatch.setattr(knowledge_sources, "link_tool", link_tool)
    return session


class TestLinkNoteSources:
    def test_wikilink_becomes_a_new_source_with_its_note_path(self, fake_db):
        tool = SimpleNamespace(id=7, name="httping")

        result = knowledge_sources.link_note_sources(
            fake_db, tool, [{"label": "docker swarm Udemy", "url": None, "wikilink": True}],
        )

        assert result == {"linked": ["docker swarm Udemy"], "created": ["docker swarm Udemy"], "skipped_urls": []}
        created = fake_db.sources[-1]
        assert created.kind == "course" and created.obsidian_note_path == "02-wiedza/docker swarm Udemy.md"

    def test_existing_source_is_reused_by_normalized_name(self, fake_db):
        tool = SimpleNamespace(id=7, name="Semgrep")

        result = knowledge_sources.link_note_sources(
            fake_db, tool, [{"label": "akademia bezpiecznego kodu", "url": None, "wikilink": True}],
        )

        assert result["created"] == [] and result["linked"] == ["Akademia Bezpiecznego Kodu"]
        assert len(fake_db.sources) == 1

    def test_bare_url_becomes_context_of_the_first_source_or_is_skipped(self, fake_db):
        tool = SimpleNamespace(id=7, name="Semgrep")
        url = "https://semgrep.dev/docs/quickstart"

        with_source = knowledge_sources.link_note_sources(fake_db, tool, [
            {"label": "Akademia Bezpiecznego Kodu", "url": None, "wikilink": True},
            {"label": None, "url": url, "wikilink": False},
        ])
        alone = knowledge_sources.link_note_sources(fake_db, SimpleNamespace(id=8, name="x"), [
            {"label": None, "url": url, "wikilink": False},
        ])

        assert with_source["skipped_urls"] == [] and fake_db.links[0].context == url
        assert alone["skipped_urls"] == [url]

    def test_note_naming_the_tool_itself_is_not_a_source(self, fake_db):
        tool = SimpleNamespace(id=7, name="serper.dev")

        result = knowledge_sources.link_note_sources(fake_db, tool, [{"label": "serper.dev", "url": None, "wikilink": True}])

        assert result == {"linked": [], "created": [], "skipped_urls": []}


def _tool_routes(monkeypatch, tool, session):
    monkeypatch.setattr("library.tool_routes.get_scoped_session", lambda: session)
    monkeypatch.setattr("library.tool_routes.knowledge_sources.sources_for_tools", lambda *_a: {tool.id: [{"id": 5, "name": "Kurs"}]})
    session.get.side_effect = lambda model, key: tool if model.__name__ == "Tool" else (
        SimpleNamespace(id=5, name="Kurs") if key == 5 else None)


class TestToolSourceRoutes:
    def _call(self, monkeypatch, body, kind="service", linked=True):
        from library.tool_routes import add_tool_source

        tool = SimpleNamespace(id=7, name="httping")
        session = MagicMock()
        _tool_routes(monkeypatch, tool, session)
        monkeypatch.setattr("library.tool_routes.knowledge_sources.link_tool",
                            lambda *_a, **_k: (SimpleNamespace(context=None), linked))
        monkeypatch.setattr("library.tool_routes.knowledge_sources.get_or_create_source",
                            lambda _s, name, kind=None: (SimpleNamespace(id=9, name=name), True))
        app = Flask(__name__)
        with app.test_request_context("/tools/7/sources", method="POST", json=body):
            g.auth = SimpleNamespace(kind=kind, user_id=None)
            return add_tool_source(7), session

    def test_add_by_name_creates_the_source(self, monkeypatch):
        (response, status), session = self._call(monkeypatch, {"name": "Nowy kurs", "kind": "course"})

        assert status == 201 and response.json["source_created"] is True
        session.commit.assert_called_once()

    def test_add_by_id_and_unknown_id(self, monkeypatch):
        from werkzeug.exceptions import NotFound

        (response, status), _ = self._call(monkeypatch, {"source_id": 5}, linked=False)
        assert status == 200 and response.json["source_created"] is False
        with pytest.raises(NotFound):
            self._call(monkeypatch, {"source_id": 99})

    def test_name_or_id_is_required_and_kind_is_checked(self, monkeypatch):
        from werkzeug.exceptions import BadRequest

        with pytest.raises(BadRequest):
            self._call(monkeypatch, {})
        with pytest.raises(BadRequest):
            self._call(monkeypatch, {"name": "x", "kind": "blog"})

    def test_remove_unlinks_or_404(self, monkeypatch):
        from werkzeug.exceptions import NotFound
        from library.tool_routes import remove_tool_source

        session = MagicMock()
        monkeypatch.setattr("library.tool_routes.get_scoped_session", lambda: session)
        monkeypatch.setattr("library.tool_routes.knowledge_sources.sources_for_tools", lambda *_a: {})
        app = Flask(__name__)
        monkeypatch.setattr("library.tool_routes.knowledge_sources.unlink_tool", lambda *_a: True)
        with app.test_request_context("/tools/7/sources/5", method="DELETE"):
            g.auth = SimpleNamespace(kind="user", user_id=1)
            assert remove_tool_source(7, 5).json == {"sources": []}
        monkeypatch.setattr("library.tool_routes.knowledge_sources.unlink_tool", lambda *_a: False)
        with app.test_request_context("/tools/7/sources/5", method="DELETE"):
            g.auth = SimpleNamespace(kind="user", user_id=1)
            with pytest.raises(NotFound):
                remove_tool_source(7, 5)
