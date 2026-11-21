"""Chapter-aware spellcheck: skipped chapter types, memory of decisions, re-analysis with a larger context."""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

pytest.importorskip("sqlalchemy")
pytest.importorskip("flask")

from flask import Flask, g
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from library import transcript_spellcheck as sc
from library import transcript_spellcheck_memory as mem
from library import transcript_spellcheck_routes as routes
from library.db.models import TranscriptSpellcheckMemory

KNOWN = {"spór", "o", "myśliwiec", "to", "jest", "tekst", "temat", "kupujcie", "teraz", "tu", "w", "temacie"}


class FakeAnalyser:
    def analyse(self, word):
        return [(0, 1, (word, word, "subst" if word.casefold() in KNOWN else "ign", [], []))]


A = FakeAnalyser()
TEXT = (
    "Wstęp aaaaa.\n\n"
    "## Temat\n\nTu jest spóromyśliwiec w temacie.\n\n"
    "## Reklama\n\nKupujcie teraz reklamowyzlepek.\n\n"
    "## Szum\n\nszumowyzlepek jest tu.\n"
)
TYPES = ["TEMAT", "REKLAMA", "SZUM"]


@pytest.fixture
def db():
    engine = create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})
    TranscriptSpellcheckMemory.__table__.create(engine)
    with Session(engine) as session:
        yield session


class TestChaptersAndSuspects:
    def test_chapters_are_numbered_like_the_ner_page(self):
        chapters = sc.chapters_of(TEXT, TYPES)
        assert [(c["position"], c["title"], c["type"]) for c in chapters] == [
            (0, "", "TEMAT"), (1, "Temat", "TEMAT"), (2, "Reklama", "REKLAMA"), (3, "Szum", "SZUM")]
        assert "## " not in "".join(c["body"] for c in chapters)

    def test_advertisement_noise_and_sources_are_never_scanned(self):
        found = sc.find_suspects(TEXT, analyser=A, chapter_types=TYPES)
        assert [(s["word"], s["chapter"], s["chapter_title"]) for s in found["suspects"]] == [
            ("aaaaa", 0, ""), ("spóromyśliwiec", 1, "Temat")]
        assert found["skipped_chapters"] == {"REKLAMA": 1, "SZUM": 1}

    def test_without_stored_types_every_chapter_is_read(self):
        words = {s["word"] for s in sc.find_suspects(TEXT, analyser=A)["suspects"]}
        assert {"reklamowyzlepek", "szumowyzlepek"} <= words

    def test_a_stale_type_list_is_ignored_not_misaligned(self):
        # two types for three chapters: aligning them would skip the wrong chapter
        found = sc.find_suspects(TEXT, analyser=A, chapter_types=["REKLAMA", "TEMAT"])
        assert found["skipped_chapters"] == {}
        assert "reklamowyzlepek" in {s["word"] for s in found["suspects"]}

    def test_context_stays_inside_the_chapter_and_a_text_without_headings_is_one_chapter(self):
        found = sc.find_suspects("Otóż spóromyśliwiec tutaj.", analyser=A)
        assert found["suspects"][0]["chapter"] == 0 and found["skipped_chapters"] == {}
        chaptered = sc.find_suspects(TEXT, analyser=A, chapter_types=TYPES)["suspects"][0]
        assert "Temat" not in chaptered["context"]

    def test_suspects_are_ordered_by_chapter_after_the_frequency_limit(self):
        text = "zzzzz yyyyy yyyyy\n\n## B\n\nxxxxx xxxxx xxxxx\n"
        found = sc.find_suspects(text, analyser=A, limit=2)
        assert [(s["word"], s["chapter"]) for s in found["suspects"]] == [("yyyyy", 0), ("xxxxx", 1)]

    def test_prompt_names_the_chapter_and_neutralises_quotes(self):
        prompt = sc.build_prompt([{"word": "x", "context": "c", "chapter_title": 'Ti"tle'},
                                  {"word": "y", "context": "d"}])
        assert "rozdział: \"Ti'tle\"" in prompt
        assert prompt.count("rozdział:") == 1


class TestMemoryService:
    def test_trusted_after_two_documents_of_the_channel(self, db):
        decision = [{"original": "Spóromyśliwiec", "decision": "accepted", "replacement": "spór o myśliwiec"}]
        mem.record_decisions(db, document_id=1, author="Kanał", decisions=decision)
        first = mem.lookup(db, "Kanał", ["spóromyśliwiec"])["spóromyśliwiec"]
        assert (first.replacement, first.documents, first.trusted) == ("spór o myśliwiec", 1, False)
        mem.record_decisions(db, document_id=1, author="Kanał", decisions=decision)  # same document again
        assert mem.lookup(db, "Kanał", ["spóromyśliwiec"])["spóromyśliwiec"].documents == 1
        mem.record_decisions(db, document_id=2, author="Kanał", decisions=decision)
        assert mem.lookup(db, "Kanał", ["spóromyśliwiec"])["spóromyśliwiec"].trusted is True

    def test_memory_is_per_channel_with_a_shared_bucket_for_documents_without_one(self, db):
        mem.record_decisions(db, document_id=1, author="Kanał A", decisions=[
            {"original": "zlepek", "decision": "accepted", "replacement": "z lepek"}])
        assert mem.lookup(db, "Kanał B", ["zlepek"]) == {}
        mem.record_decisions(db, document_id=2, author=None, decisions=[
            {"original": "zlepek", "decision": "rejected"}])
        assert mem.lookup(db, "Kanał B", ["zlepek"])["zlepek"].decision == "rejected"  # shared bucket
        assert mem.lookup(db, "Kanał A", ["zlepek"])["zlepek"].decision == "accepted"  # the channel wins

    def test_the_newest_decision_wins(self, db):
        mem.record_decisions(db, document_id=1, author="K", decisions=[
            {"original": "zlepek", "decision": "accepted", "replacement": "z lepek"}])
        mem.record_decisions(db, document_id=2, author="K", decisions=[{"original": "zlepek", "decision": "rejected"}])
        assert mem.lookup(db, "K", ["zlepek"])["zlepek"].decision == "rejected"
        mem.record_decisions(db, document_id=3, author="K", decisions=[
            {"original": "zlepek", "decision": "accepted", "replacement": "zlep ek"}])
        found = mem.lookup(db, "K", ["zlepek"])["zlepek"]
        assert (found.decision, found.replacement) == ("accepted", "zlep ek")
        assert db.query(TranscriptSpellcheckMemory).count() == 1

    def test_the_spelling_confirmed_by_most_documents_wins(self, db):
        for doc, replacement in ((1, "a b"), (2, "a b"), (3, "a  c")):
            mem.record_decisions(db, document_id=doc, author="K", decisions=[
                {"original": "abc", "decision": "accepted", "replacement": replacement}])
        assert mem.lookup(db, "K", ["abc"])["abc"].replacement == "a b"

    @pytest.mark.parametrize("decision", [
        "x", {"decision": "accepted", "replacement": "b"}, {"original": "a", "decision": "maybe"},
        {"original": "a", "decision": "accepted"}, {"original": "a", "decision": "accepted", "replacement": "A"},
        {"original": " ", "decision": "rejected"}, {"original": "a" * 300, "decision": "rejected"},
    ])
    def test_invalid_decisions(self, db, decision):
        with pytest.raises(mem.MemoryValidationError):
            mem.record_decisions(db, document_id=1, author="K", decisions=[decision])

    def test_decision_list_bounds_and_forget(self, db):
        for bad in (None, [], [{"original": "a", "decision": "rejected"}] * (mem.MAX_DECISIONS + 1)):
            with pytest.raises(mem.MemoryValidationError):
                mem.record_decisions(db, document_id=1, author="K", decisions=bad)
        mem.record_decisions(db, document_id=1, author="K", decisions=[{"original": "abc", "decision": "rejected"}])
        remembered = mem.lookup(db, "K", ["abc"])["abc"]
        assert mem.forget(db, remembered.id) is True and mem.forget(db, remembered.id) is False
        assert mem.lookup(db, "K", ["abc"]) == {}


class TestSplitAndAnalyse:
    def _doc(self):
        return SimpleNamespace(id=7, text=TEXT, byline="Kanał", chapter_types=TYPES)

    def test_split_by_memory(self):
        suspects = [{"word": "aaaaa", "count": 1, "context": "c", "chapter": 0},
                    {"word": "bbbbb", "count": 2, "context": "d", "chapter": 1, "chapter_title": "T"},
                    {"word": "ccccc", "count": 1, "context": "e", "chapter": 2}]
        remembered = {"bbbbb": mem.Remembered(5, "bbbbb", "b b b", "accepted", 2, 3),
                      "ccccc": mem.Remembered(6, "ccccc", None, "rejected", 1, 1)}
        fresh, proposals, rejected = sc.split_by_memory(suspects, remembered)
        assert [s["word"] for s in fresh] == ["aaaaa"]
        assert proposals == [{"original": "bbbbb", "replacement": "b b b", "confidence": "high", "count": 2,
                              "context": "d", "chapter": 1, "chapter_title": "T", "source": "memory",
                              "trusted": True, "memory_documents": 2, "memory_id": 5}]
        assert rejected == [{"word": "ccccc", "count": 1, "context": "e", "chapter": 2, "memory_id": 6}]
        untrusted = sc.split_by_memory(suspects[1:2], {"bbbbb": mem.Remembered(5, "bbbbb", "b", "accepted", 1, 1)})
        assert untrusted[1][0]["trusted"] is False and untrusted[1][0]["confidence"] == "medium"

    def test_only_unknown_words_reach_the_model(self, db):
        mem.record_decisions(db, document_id=1, author="Kanał", decisions=[
            {"original": "spóromyśliwiec", "decision": "accepted", "replacement": "spór o myśliwiec"}])
        mem.record_decisions(db, document_id=2, author="Kanał", decisions=[
            {"original": "spóromyśliwiec", "decision": "accepted", "replacement": "spór o myśliwiec"}])
        mem.record_decisions(db, document_id=1, author="Kanał", decisions=[{"original": "aaaaa", "decision": "rejected"}])
        with patch.object(sc, "propose") as propose:
            result = sc.analyse_document(db, self._doc(), model="m", analyser=A)
        propose.assert_not_called()  # everything was settled before: no model call at all
        assert result["model_calls"] == 0 and result["from_memory"] == 1
        assert [(p["original"], p["source"], p["trusted"]) for p in result["proposals"]] == [
            ("spóromyśliwiec", "memory", True)]
        assert [item["word"] for item in result["known_rejected"]] == ["aaaaa"]
        assert result["skipped_chapters"] == {"REKLAMA": 1, "SZUM": 1}

    def test_the_rest_goes_to_the_model_and_memory_comes_first(self, db):
        mem.record_decisions(db, document_id=1, author="Kanał", decisions=[
            {"original": "spóromyśliwiec", "decision": "accepted", "replacement": "spór o myśliwiec"}])
        answer = {"proposals": [{"original": "aaaaa", "replacement": "a a", "source": "model"}], "rejected": {},
                  "model": "m", "model_calls": 1, "usage": None}
        with patch.object(sc, "propose", return_value=answer) as propose:
            result = sc.analyse_document(db, self._doc(), model="m", analyser=A)
        assert [s["word"] for s in propose.call_args.args[0]] == ["aaaaa"]
        assert [p["original"] for p in result["proposals"]] == ["spóromyśliwiec", "aaaaa"]
        assert result["suspects"] == 2 and result["model_calls"] == 1

    def test_dry_run_reports_the_fate_of_every_suspect_without_a_model(self, db):
        mem.record_decisions(db, document_id=1, author="Kanał", decisions=[{"original": "aaaaa", "decision": "rejected"}])
        with patch.object(sc, "propose") as propose:
            result = sc.analyse_document(db, self._doc(), model="m", dry_run=True, analyser=A)
        propose.assert_not_called()
        assert {s["word"]: s["status"] for s in result["suspects"]} == {"aaaaa": "rejected", "spóromyśliwiec": "new"}
        assert result["to_model"] == 1


def _response(text):
    return SimpleNamespace(response_text=text, usage=None)


class TestWindow:
    def test_cuts_at_word_boundaries_and_stays_near_the_requested_size(self):
        body = "aaa " * 200 + "spóromyśliwiec" + " bbb" * 200
        start = body.index("spóromyśliwiec")
        window = sc._window(body, start, len("spóromyśliwiec"), 50)
        assert "spóromyśliwiec" in window
        assert window.startswith("aaa") and window.endswith("bbb")
        assert len(window) <= 50 * 2 + len("spóromyśliwiec") + 2

    def test_short_body_is_returned_whole(self):
        assert sc._window("ala  ma\nkota spór", 12, 4, 400) == "ala ma kota spór"


class TestReanalyze:
    BODY = "Na początku mówimy o sprawach ogólnych. " * 6 + "Teraz spóromyśliwiec został wybrany. " + "Potem koniec. " * 6
    TEXT = "## Temat\n\n" + BODY + "\n\n## Reklama\n\nKupujcie spóromyśliwiec teraz.\n"

    def _run(self, answer, items, context_chars=400, text=None):
        with patch("library.ai.ai_ask", return_value=_response(answer)) as ask, \
                patch("library.transcript_spellcheck.llm_model_registry.model_details", return_value={}), \
                patch("library.entity_description_batch.supports_structured_output", return_value=False), \
                patch("library.event_description.usage_summary", return_value={}), \
                patch("library.entity_description_batch._sum_usage", return_value=None):
            return sc.reanalyze(items, text or self.TEXT, model="m", chapter_types=["TEMAT", "REKLAMA"],
                                context_chars=context_chars, document_id=9, analyser=A), ask

    def test_sends_a_longer_context_and_the_earlier_proposal(self):
        answer = ('{"corrections":[{"id":0,"replacement":"spór o myśliwiec","confidence":"high",'
                  '"reason":"Mówca ma na myśli spór o samolot."}]}')
        result, ask = self._run(answer, [{"original": "spóromyśliwiec", "replacement": "spór o mysliwiec", "chapter": 1}])
        prompt = ask.call_args.args[0]
        assert "wcześniejsza propozycja: \"spór o mysliwiec\"" in prompt and "rozdział: \"Temat\"" in prompt
        assert "Na początku mówimy" in prompt and "Potem koniec" in prompt  # far more than the 90 characters
        assert ask.call_args.kwargs["operation"] == "transcript_spellcheck_reanalysis"
        assert ask.call_args.kwargs["document_id"] == 9
        item = result["results"][0]
        assert (item["replacement"], item["changed"], item["confidence"]) == ("spór o myśliwiec", True, "high")
        assert item["reason"] == "Mówca ma na myśli spór o samolot." and item["chapter"] == 1
        assert item["context_chars"] == 400 and len(item["context"]) > 200

    def test_larger_steps_give_more_text(self):
        answer = '{"corrections":[{"id":0,"replacement":"spór o myśliwiec","confidence":"low","reason":null}]}'
        small = self._run(answer, [{"original": "spóromyśliwiec"}], context_chars=100)[0]["results"][0]["context"]
        large = self._run(answer, [{"original": "spóromyśliwiec"}], context_chars=900)[0]["results"][0]["context"]
        assert len(large) > len(small) and small in large
        assert self._run(answer, [{"original": "spóromyśliwiec"}], context_chars=100)[0]["results"][0]["reason"] is None

    def test_same_answer_is_not_a_change(self):
        answer = '{"corrections":[{"id":0,"replacement":"Spór o myśliwiec","confidence":"high","reason":"x"}]}'
        item = self._run(answer, [{"original": "spóromyśliwiec", "replacement": "spór o myśliwiec"}])[0]["results"][0]
        assert item["changed"] is False

    def test_an_invented_word_keeps_the_old_proposal(self):
        answer = '{"corrections":[{"id":0,"replacement":"spór o myśliwcc","confidence":"high","reason":"x"}]}'
        result, _ = self._run(answer, [{"original": "spóromyśliwiec", "replacement": "spór o myśliwiec"}])
        assert result["results"][0]["replacement"] is None and result["results"][0]["rejected"] == "unknown_word"
        assert result["rejected"] == {"unknown_word": 1}

    def test_a_word_no_longer_in_the_text_costs_no_call_and_a_skipped_chapter_is_not_searched(self):
        result, ask = self._run("{}", [{"original": "nieistniejące"}, {"original": "spóromyśliwiec", "chapter": 2}],
                                text="## Temat\n\nTekst.\n\n## Reklama\n\nspóromyśliwiec\n")
        ask.assert_not_called()
        assert [r["rejected"] for r in result["results"]] == ["not_found", "not_found"]
        assert result["model_calls"] == 0 and result["rejected"] == {"not_found": 2}

    def test_unparseable_answer_keeps_every_proposal(self):
        result, _ = self._run("nope", [{"original": "spóromyśliwiec"}])
        assert result["results"][0]["rejected"] == "unparseable_answer" and result["results"][0]["replacement"] is None

    def test_items_are_batched_and_results_keep_their_order(self):
        text = "## T\n\n" + " ".join(f"slowo{i:02d}x" for i in range(23)) + "\n"
        items = [{"original": f"slowo{i:02d}x"} for i in range(23)]
        reply = '{"corrections":[]}'
        with patch("library.ai.ai_ask", return_value=_response(reply)) as ask, \
                patch("library.transcript_spellcheck.llm_model_registry.model_details", return_value={}), \
                patch("library.entity_description_batch.supports_structured_output", return_value=False), \
                patch("library.event_description.usage_summary", return_value={}), \
                patch("library.entity_description_batch._sum_usage", return_value=None):
            result = sc.reanalyze(items, text, model="m", analyser=A)
        assert ask.call_count == 3 and [r["original"] for r in result["results"]] == [i["original"] for i in items]


@pytest.fixture
def client(monkeypatch):
    session = MagicMock()
    session.get.return_value = SimpleNamespace(id=1, document_type="youtube", text=TEXT, byline="Kanał",
                                               chapter_types=TYPES)
    monkeypatch.setattr(routes, "get_scoped_session", lambda: session)
    monkeypatch.setattr(routes.spellcheck, "default_model", lambda s: "test")
    monkeypatch.setattr(routes.llm_model_registry, "is_selectable", lambda model, task: model == "test")
    app = Flask(__name__)
    app.register_blueprint(routes.bp)
    kind = {"value": "user"}

    @app.before_request
    def _auth():
        g.auth = SimpleNamespace(kind=kind["value"])

    test_client = app.test_client()
    test_client.session, test_client.kind = session, kind
    return test_client


class TestRoutes:
    def test_reanalyze_passes_the_items_and_the_context_step(self, client):
        answer = {"results": [], "rejected": {}, "model": "test", "model_calls": 0, "usage": None, "context_chars": 900}
        body = {"items": [{"original": "abc", "replacement": "a b", "chapter": 1}], "context_chars": 900}
        with patch.object(routes.spellcheck, "reanalyze", return_value=answer) as reanalyze:
            response = client.post("/document/1/transcript_spellcheck/reanalyze", json=body)
        assert response.status_code == 200 and response.get_json()["context_chars"] == 900
        args, kwargs = reanalyze.call_args
        assert args[0] == [{"original": "abc", "replacement": "a b", "chapter": 1}] and args[1] == TEXT
        assert kwargs["context_chars"] == 900 and kwargs["chapter_types"] == TYPES and kwargs["model"] == "test"
        client.session.commit.assert_not_called()

    @pytest.mark.parametrize("body", [
        {}, {"items": []}, {"items": "x"}, {"items": [1]}, {"items": [{"original": ""}]},
        {"items": [{"original": "a", "chapter": -1}]}, {"items": [{"original": "a", "replacement": 5}]},
        {"items": [{"original": "a"}], "context_chars": 50}, {"items": [{"original": "a"}], "context_chars": 99999},
        {"items": [{"original": "a"}], "context_chars": "400"}, {"items": [{"original": "a"}], "model": "evil"},
        {"items": [{"original": "a"}] * 81},
    ])
    def test_reanalyze_rejects_bad_requests(self, client, body):
        assert client.post("/document/1/transcript_spellcheck/reanalyze", json=body).status_code == 400

    def test_reanalyze_needs_a_transcript_and_hides_model_errors(self, client):
        with patch.object(routes.spellcheck, "reanalyze", side_effect=RuntimeError("boom")):
            response = client.post("/document/1/transcript_spellcheck/reanalyze", json={"items": [{"original": "a"}]})
        assert response.status_code == 502 and "boom" not in response.get_data(as_text=True)
        client.session.get.return_value = SimpleNamespace(id=1, document_type="webpage", text="x", byline=None,
                                                          chapter_types=None)
        assert client.post("/document/1/transcript_spellcheck/reanalyze",
                           json={"items": [{"original": "a"}]}).status_code == 400
        client.session.get.return_value = None
        assert client.post("/document/1/transcript_spellcheck/reanalyze",
                           json={"items": [{"original": "a"}]}).status_code == 404

    def test_decisions_are_stored_for_the_documents_channel_and_committed(self, client):
        decisions = [{"original": "abc", "decision": "accepted", "replacement": "a b"}]
        with patch.object(routes.memory, "record_decisions", return_value={"accepted": 1, "rejected": 0}) as record:
            response = client.post("/document/1/transcript_spellcheck/decisions", json={"decisions": decisions})
        assert response.status_code == 200 and response.get_json()["accepted"] == 1
        assert record.call_args.kwargs == {"document_id": 1, "author": "Kanał", "decisions": decisions}
        client.session.commit.assert_called_once()

    def test_invalid_decisions_are_400_and_roll_back(self, client):
        with patch.object(routes.memory, "record_decisions", side_effect=mem.MemoryValidationError("zły wpis")):
            response = client.post("/document/1/transcript_spellcheck/decisions", json={"decisions": [1]})
        assert response.status_code == 400 and response.get_json()["message"] == "zły wpis"
        client.session.rollback.assert_called_once()
        client.session.commit.assert_not_called()

    def test_writing_needs_a_user_or_service_key(self, client):
        client.kind["value"] = "reader"
        assert client.post("/document/1/transcript_spellcheck/decisions",
                           json={"decisions": []}).status_code == 403
        assert client.delete("/transcript_spellcheck/memory/3").status_code == 403

    def test_forget_removes_one_entry_or_404(self, client):
        with patch.object(routes.memory, "forget", return_value=True):
            assert client.delete("/transcript_spellcheck/memory/3").get_json()["id"] == 3
        with patch.object(routes.memory, "forget", return_value=False):
            assert client.delete("/transcript_spellcheck/memory/3").status_code == 404
