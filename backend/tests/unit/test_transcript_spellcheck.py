"""Dictionary suspects and validated model proposals for speech-to-text slips (no real model call)."""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from library import transcript_spellcheck as sc

KNOWN = {"spór", "o", "myśliwiec", "myśliwce", "to", "jest", "tekst", "temat", "ostatni", "zamyka", "granicę"}


class FakeAnalyser:
    """Stands in for Morfeusz: a word is known when it is in KNOWN (case-insensitive)."""

    def analyse(self, word):
        tag = "subst" if word.casefold() in KNOWN else "ign"
        return [(0, 1, (word, word, tag, [], []))]


A = FakeAnalyser()


class TestFindSuspects:
    def test_flags_glued_word_with_context(self):
        text = "Otóż mamy włosko-niemiecki spóromyśliwiec. Jak państwo pamiętacie."
        found = sc.find_suspects(text, analyser=A)
        words = {s["word"]: s for s in found["suspects"]}
        assert "spóromyśliwiec" in words
        assert "spóromyśliwiec" in words["spóromyśliwiec"]["context"]

    def test_skips_fillers_short_words_and_names(self):
        found = sc.find_suspects("yyy hym abc Taiz zamyka granicę xyzqw.", analyser=A)
        assert [s["word"] for s in found["suspects"]] == ["xyzqw"]
        assert found["skipped"] == {"fillers": 2, "short": 1, "capitalized": 1}

    def test_a_term_used_often_is_not_a_slip(self):
        found = sc.find_suspects("hantawirus " * 4 + "zlepek", analyser=A)
        assert [s["word"] for s in found["suspects"]] == ["zlepek"]
        assert found["skipped"]["repeated"] == 1

    def test_limit_keeps_most_frequent(self):
        text = "aaaaa bbbbb bbbbb ccccc"
        found = sc.find_suspects(text, analyser=A, limit=1)
        assert [s["word"] for s in found["suspects"]] == ["bbbbb"]
        assert found["skipped"]["over_limit"] == 2


class TestValidateReplacement:
    def test_accepts_split_into_known_words(self):
        assert sc.validate_replacement("spóromyśliwiec", "spór o myśliwiec", analyser=A) == "spór o myśliwiec"

    @pytest.mark.parametrize("value,reason", [
        (None, "!no_proposal"), (5, "!not_text"), ("   ", "!unchanged"), ("spóromyśliwiec", "!unchanged"),
        ("spór o myśliwiec http://x.pl", "!not_words"), ("spór 2 myśliwiec", "!not_words"),
        ("to jest ostatni temat tekst", "!not_words"), ("zupełnie coś innego", "!too_different"),
        ("spór o myśliwcc", "!unknown_word"),
    ])
    def test_rejects(self, value, reason):
        assert sc.validate_replacement("spóromyśliwiec", value, analyser=A) == reason


class TestParseAnswer:
    def test_fenced_and_prose_around_json(self):
        raw = 'Oto wynik:\n```json\n{"corrections":[{"id":0,"replacement":"x","confidence":"high"}]}\n```'
        assert sc.parse_answer(raw)[0]["id"] == 0

    @pytest.mark.parametrize("raw", [None, "", "nope", "[1]", '{"corrections": 5}'])
    def test_garbage_is_none(self, raw):
        assert sc.parse_answer(raw) is None


def _response(text):
    return SimpleNamespace(response_text=text, usage=None)


class TestPropose:
    suspects = [
        {"word": "spóromyśliwiec", "count": 1, "context": "ctx a"},
        {"word": "hallucinated", "count": 1, "context": "ctx b"},
        {"word": "nothing", "count": 1, "context": "ctx c"},
    ]

    def _run(self, answer):
        with patch("library.ai.ai_ask", return_value=_response(answer)) as ask, \
                patch("library.transcript_spellcheck.llm_model_registry.model_details", return_value={}), \
                patch("library.entity_description_batch.supports_structured_output", return_value=False), \
                patch("library.event_description.usage_summary", return_value={}), \
                patch("library.entity_description_batch._sum_usage", return_value=None):
            return sc.propose(self.suspects, model="m", document_id=1, analyser=A), ask

    def test_keeps_valid_drops_invented_missing_and_null(self):
        answer = ('{"corrections":[{"id":0,"replacement":"spór o myśliwiec","confidence":"high"},'
                  '{"id":1,"replacement":"zmyślone słowo","confidence":"high"},'
                  '{"id":9,"replacement":"x","confidence":"low"}]}')
        result, ask = self._run(answer)
        assert [(p["original"], p["replacement"], p["confidence"]) for p in result["proposals"]] == [
            ("spóromyśliwiec", "spór o myśliwiec", "high")]
        assert result["rejected"] == {"too_different": 1, "missing_answer": 1}
        assert ask.call_count == 1
        assert ask.call_args.kwargs["operation"] == "transcript_spellcheck" and ask.call_args.kwargs["document_id"] == 1

    def test_unparseable_answer_is_nothing_found_not_an_error(self):
        result, _ = self._run("I cannot help")
        assert result["proposals"] == [] and result["rejected"] == {"unparseable_answer": 3}

    def test_unknown_confidence_is_low(self):
        answer = '{"corrections":[{"id":0,"replacement":"spór o myśliwiec","confidence":"certain"}]}'
        assert self._run(answer)[0]["proposals"][0]["confidence"] == "low"


@pytest.fixture
def client(monkeypatch):
    pytest.importorskip("flask")
    from flask import Flask

    from library import transcript_spellcheck_routes as routes

    session = MagicMock()
    session.get.return_value = SimpleNamespace(document_type="youtube", text="Otóż spóromyśliwiec.")
    monkeypatch.setattr(routes, "get_scoped_session", lambda: session)
    monkeypatch.setattr(sc, "default_model", lambda s: "test")
    monkeypatch.setattr(sc.llm_model_registry, "is_selectable", lambda model, task: model == "test")
    monkeypatch.setattr(sc, "_analyser", lambda: A)
    app = Flask(__name__)
    app.register_blueprint(routes.bp)
    client = app.test_client()
    client.session = session
    return client


class TestRoutes:
    def test_dry_run_lists_suspects_without_model(self, client):
        with patch("library.ai.ai_ask") as ask:
            data = client.post("/document/1/transcript_spellcheck", json={"dry_run": True}).get_json()
        assert data["suspects"][0]["word"] == "spóromyśliwiec" and data["dry_run"] is True
        ask.assert_not_called()
        client.session.commit.assert_not_called()

    def test_proposals_are_not_stored(self, client):
        result = {"proposals": [{"original": "a", "replacement": "b"}], "rejected": {}, "model": "test",
                  "model_calls": 1, "usage": None}
        with patch.object(sc, "propose", return_value=result) as propose:
            response = client.post("/document/1/transcript_spellcheck", json={"model": "test"})
        assert response.status_code == 200 and response.get_json()["proposals"][0]["replacement"] == "b"
        propose.assert_called_once()
        client.session.commit.assert_not_called()

    @pytest.mark.parametrize("body", [{"model": "evil"}, {"dry_run": "yes"}, []])
    def test_bad_requests(self, client, body):
        assert client.post("/document/1/transcript_spellcheck", json=body).status_code == 400

    def test_not_a_transcript(self, client):
        client.session.get.return_value = SimpleNamespace(document_type="webpage", text="x")
        assert client.post("/document/1/transcript_spellcheck", json={}).status_code == 400

    def test_unknown_document(self, client):
        client.session.get.return_value = None
        assert client.post("/document/1/transcript_spellcheck", json={}).status_code == 404

    def test_model_failure_is_502(self, client):
        with patch.object(sc, "propose", side_effect=RuntimeError("boom")):
            response = client.post("/document/1/transcript_spellcheck", json={})
        assert response.status_code == 502 and "boom" not in response.get_data(as_text=True)

    def test_model_setting_roundtrip(self, client):
        with patch("library.transcript_spellcheck_routes.app_settings") as settings, \
                patch.object(sc.llm_model_registry, "selectable_models", return_value=[]):
            settings.get_setting.return_value = None
            assert client.get("/transcript_spellcheck/model").status_code == 200
            assert client.put("/transcript_spellcheck/model", json={"model": "test"}).status_code == 200
            assert client.put("/transcript_spellcheck/model", json={"model": "evil"}).status_code == 400


def test_real_morfeusz_flags_the_reported_slip():
    pytest.importorskip("morfeusz2")
    found = sc.find_suspects("Otóż mamy włosko-niemiecki spóromyśliwiec. To jest tekst o temacie.")
    assert [s["word"] for s in found["suspects"]] == ["spóromyśliwiec"]
    assert sc.is_known_word("myśliwiec") and sc.is_known_word("Polska")
