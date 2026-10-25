"""Unit tests for library.place_mention_gazetteer — text-grounded place detection.

Pure functions; the gazetteer store is empty by default (tests/unit/conftest.py).
"""

import pytest

pytest.importorskip("unidecode")

from library import ner_gazetteer_store, place_mention_gazetteer  # noqa: E402
from library.ner_gazetteer_store import GazetteerEntry  # noqa: E402

# Real excerpts from doc #10872.
KOENIGSBERG = "w przypadku próby izolacji Kaliningradu, czyli królewca jest oficjalnym stanowiskiem rosyjskiego MSZ"
OBLAST = "Wyraźnie przywołany obwód kaliningradzki. A blokada obwodu kaliningradzkiego i w obwodzie kaliningradzkim."
GAP = "rozmieszczenie wojsk sojusznicczych przez przesmyk suwalski. Yyy to tak na marginesie"


class TestDetectPlaceMentions:
    def test_lowercase_krolewiec_is_kaliningrad(self):
        assert place_mention_gazetteer.detect_place_mentions(KOENIGSBERG) == {"Kaliningrad": {"królewca": 1}}

    def test_every_inflected_form_of_krolewiec(self):
        text = "Królewiec, Królewca, królewcu, królewcem i z Królewcem"
        found = place_mention_gazetteer.detect_place_mentions(text)["Kaliningrad"]
        assert sum(found.values()) == 5

    def test_kaliningrad_oblast_all_cases(self):
        found = place_mention_gazetteer.detect_place_mentions(OBLAST)
        assert found == {"Obwód Kaliningradzki": {
            "obwód kaliningradzki": 1, "obwodu kaliningradzkiego": 1, "obwodzie kaliningradzkim": 1,
        }}

    def test_suwalki_gap(self):
        assert place_mention_gazetteer.detect_place_mentions(GAP) == {"Przesmyk Suwalski": {"przesmyk suwalski": 1}}

    def test_surface_keeps_original_case_and_diacritics(self):
        found = place_mention_gazetteer.detect_place_mentions("Przesmyku Suwalskiego broni NATO")
        assert found == {"Przesmyk Suwalski": {"Przesmyku Suwalskiego": 1}}

    @pytest.mark.parametrize("text", [
        "królewskie miody prosto z pasieki, oferta na królewskimody.pl",
        "obwód lubelski i obwód moskiewski",
        "przesmyk panamski",
        "kaliningradzki port bez obwodu",
        "",
    ])
    def test_unrelated_text_is_not_matched(self, text):
        assert place_mention_gazetteer.detect_place_mentions(text) == {}

    def test_mentions_spacy_already_reported_are_not_counted_twice(self):
        text = "Rosja grozi wojną o Królewiec. Potem o królewca."
        raw = [{"text": "Królewiec", "label": "placeName"}]
        assert place_mention_gazetteer.detect_place_mentions(text, raw) == {"Kaliningrad": {"królewca": 1}}

    def test_only_the_reported_number_of_identical_surfaces_is_subtracted(self):
        text = "Królewiec i znów Królewiec, a trzeci Królewiec"
        raw = [{"text": "Królewiec", "label": "placeName"}]
        assert place_mention_gazetteer.detect_place_mentions(text, raw) == {"Kaliningrad": {"Królewiec": 2}}

    def test_whitespace_and_hyphen_between_tokens_is_normalized_in_surface(self):
        found = place_mention_gazetteer.detect_place_mentions("obwód\n kaliningradzki")
        assert found == {"Obwód Kaliningradzki": {"obwód kaliningradzki": 1}}

    def test_match_offsets_survive_characters_unidecode_would_expand(self):
        # "ß" -> "ss" in plain unidecode would shift every later offset.
        found = place_mention_gazetteer.detect_place_mentions("Straße ß ß ß przesmyk suwalski")
        assert found == {"Przesmyk Suwalski": {"przesmyk suwalski": 1}}


class TestDatabaseEntries:
    def test_database_entry_extends_the_seed(self, monkeypatch):
        entry = GazetteerEntry(ner_gazetteer_store.KIND_PLACE_MENTION, "Brama Smoleńska", ("bram* smolensk*",))
        monkeypatch.setattr(ner_gazetteer_store, "get_entries", lambda kind: (entry,) if kind == "place_mention" else ())
        monkeypatch.setattr(ner_gazetteer_store, "cache_version", lambda: 987_654)
        found = place_mention_gazetteer.detect_place_mentions("Wojska stoją przy Bramie Smoleńskiej, a królewca nie ma.")
        assert found == {"Brama Smoleńska": {"Bramie Smoleńskiej": 1}, "Kaliningrad": {"królewca": 1}}

    def test_database_pattern_can_add_to_an_existing_name(self, monkeypatch):
        entry = GazetteerEntry(ner_gazetteer_store.KIND_PLACE_MENTION, "kaliningrad", ("koenigsberg*",))
        monkeypatch.setattr(ner_gazetteer_store, "get_entries", lambda kind: (entry,) if kind == "place_mention" else ())
        monkeypatch.setattr(ner_gazetteer_store, "cache_version", lambda: 987_655)
        found = place_mention_gazetteer.detect_place_mentions("Koenigsberg i królewca")
        assert list(found) == ["Kaliningrad"]
        assert sum(found["Kaliningrad"].values()) == 2
