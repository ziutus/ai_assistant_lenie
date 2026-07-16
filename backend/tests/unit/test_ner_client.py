"""Unit tests for library/ner_client.py — NER microservice client + aggregation."""

from unittest.mock import MagicMock, patch

import pytest

pytest.importorskip("requests")

import requests  # noqa: E402

from library.ner_client import (  # noqa: E402
    ENTITY_TYPES,
    MAX_TEXT_CHARS,
    aggregate_entities,
    aggregate_entities_detailed,
    extract_entities,
    extract_entities_strict,
    is_available,
    NERExtractionError,
    warmup_async,
)


def _response(entities):
    resp = MagicMock()
    resp.json.return_value = {"entities": entities}
    resp.raise_for_status.return_value = None
    return resp


class TestIsAvailable:
    def test_healthy_service_returns_true(self):
        resp = MagicMock(ok=True)
        with patch("library.ner_client.requests.get", return_value=resp) as mock_get:
            with patch("library.ner_client._service_url", return_value="http://ner:8090"):
                assert is_available() is True
        assert mock_get.call_args.args[0] == "http://ner:8090/healthz"

    def test_error_status_returns_false(self):
        resp = MagicMock(ok=False)
        with patch("library.ner_client.requests.get", return_value=resp):
            with patch("library.ner_client._service_url", return_value="http://ner:8090"):
                assert is_available() is False

    def test_unreachable_service_returns_false(self):
        with patch("library.ner_client.requests.get", side_effect=requests.ConnectionError("boom")):
            with patch("library.ner_client._service_url", return_value="http://ner:8090"):
                assert is_available() is False


class TestExtractEntities:
    def test_returns_entities_from_service(self):
        entities = [{"text": "Donald Tusk", "label": "persName", "lemma": "Donald Tusk", "start": 0, "end": 11}]
        with patch("library.ner_client.requests.post", return_value=_response(entities)) as mock_post:
            with patch("library.ner_client._service_url", return_value="http://ner:8090"):
                result = extract_entities("Donald Tusk spotkał się z premierem.")

        assert result == entities
        assert mock_post.call_args.args[0] == "http://ner:8090/ner"

    def test_empty_text_short_circuits(self):
        with patch("library.ner_client.requests.post") as mock_post:
            assert extract_entities("") == []
            assert extract_entities("   ") == []
        mock_post.assert_not_called()

    def test_service_down_returns_empty(self):
        with patch("library.ner_client.requests.post", side_effect=requests.ConnectionError("boom")):
            with patch("library.ner_client._service_url", return_value="http://ner:8090"):
                assert extract_entities("tekst") == []

    def test_invalid_json_returns_empty(self):
        resp = MagicMock()
        resp.raise_for_status.return_value = None
        resp.json.side_effect = ValueError("not json")
        with patch("library.ner_client.requests.post", return_value=resp):
            with patch("library.ner_client._service_url", return_value="http://ner:8090"):
                assert extract_entities("tekst") == []

    def test_unexpected_payload_shape_returns_empty(self):
        resp = MagicMock()
        resp.raise_for_status.return_value = None
        resp.json.return_value = {"entities": "oops"}
        with patch("library.ner_client.requests.post", return_value=resp):
            with patch("library.ner_client._service_url", return_value="http://ner:8090"):
                assert extract_entities("tekst") == []

    def test_long_text_processed_in_windows(self):
        """Tekst dłuższy niż MAX_TEXT_CHARS idzie oknami — wcześniej był ucinany do pierwszego okna."""
        with patch("library.ner_client.requests.post", return_value=_response([])) as mock_post:
            with patch("library.ner_client._service_url", return_value="http://ner:8090"):
                extract_entities("x" * (MAX_TEXT_CHARS + 500))
        assert mock_post.call_count == 2
        sent_lengths = [c.kwargs["json"]["text"] for c in mock_post.call_args_list]
        assert [len(t) for t in sent_lengths] == [MAX_TEXT_CHARS, 500]

    def test_window_results_are_concatenated(self):
        first = [{"text": "Tusk", "label": "persName", "lemma": "Tusk"}]
        second = [{"text": "Kijów", "label": "placeName", "lemma": "Kijów"}]
        with patch("library.ner_client.requests.post",
                   side_effect=[_response(first), _response(second)]):
            with patch("library.ner_client._service_url", return_value="http://ner:8090"):
                result = extract_entities("x" * (MAX_TEXT_CHARS + 500))
        assert result == first + second

    def test_window_cut_backs_up_to_whitespace(self):
        """Słowo na granicy okna nie jest przecinane w pół — cięcie cofa się do spacji."""
        text = "a" * (MAX_TEXT_CHARS - 10) + " Konstantynopol upadł"
        with patch("library.ner_client.requests.post", return_value=_response([])) as mock_post:
            with patch("library.ner_client._service_url", return_value="http://ner:8090"):
                extract_entities(text)
        windows = [c.kwargs["json"]["text"] for c in mock_post.call_args_list]
        assert any("Konstantynopol" in w for w in windows)
        assert len(windows[0]) == MAX_TEXT_CHARS - 10  # cięcie na spacji, nie w środku słowa

    def test_failed_window_returns_partial_results(self):
        """Padnięcie serwisu w trakcie — zwracamy to, co już zebrano, bez dobijania kolejnych okien."""
        first = [{"text": "Tusk", "label": "persName", "lemma": "Tusk"}]
        with patch("library.ner_client.requests.post",
                   side_effect=[_response(first), requests.ConnectionError("boom")]) as mock_post:
            with patch("library.ner_client._service_url", return_value="http://ner:8090"):
                result = extract_entities("x" * (3 * MAX_TEXT_CHARS))
        assert result == first
        assert mock_post.call_count == 2  # trzecie okno pominięte

    def test_strict_first_window_failure_raises(self):
        with patch("library.ner_client.requests.post", side_effect=requests.ConnectionError("boom")):
            with patch("library.ner_client._service_url", return_value="http://ner:8090"):
                with pytest.raises(NERExtractionError, match="window 1"):
                    extract_entities_strict("tekst")

    def test_strict_later_window_failure_discards_partial_result(self):
        first = [{"text": "Tusk", "label": "persName", "lemma": "Tusk"}]
        with patch(
            "library.ner_client.requests.post",
            side_effect=[_response(first), requests.ConnectionError("boom")],
        ):
            with patch("library.ner_client._service_url", return_value="http://ner:8090"):
                with pytest.raises(NERExtractionError, match="window 2"):
                    extract_entities_strict("x" * (MAX_TEXT_CHARS + 500))


class TestWarmupAsync:
    def test_fires_probe_in_background(self):
        import threading

        called = threading.Event()

        def fake_post(*args, **kwargs):
            called.set()
            return _response([])

        with patch("library.ner_client.requests.post", side_effect=fake_post):
            with patch("library.ner_client._service_url", return_value="http://ner:8090"):
                warmup_async()
                assert called.wait(timeout=2)

    def test_service_down_does_not_raise(self):
        with patch("library.ner_client.requests.post", side_effect=requests.ConnectionError("boom")):
            with patch("library.ner_client._service_url", return_value="http://ner:8090"):
                warmup_async()  # fire-and-forget — nie może rzucić wyjątku


class TestAggregateEntities:
    def test_groups_inflected_variants_by_lemma(self):
        entities = [
            {"text": "Donald Tusk", "label": "persName", "lemma": "Donald Tusk"},
            {"text": "Tuska", "label": "persName", "lemma": "Tusk"},
            {"text": "Tusk", "label": "persName", "lemma": "Tusk"},
        ]
        assert aggregate_entities(entities) == {
            ("persName", "Donald Tusk"): 1,
            ("persName", "Tusk"): 2,
        }

    def test_falls_back_to_surface_text_without_lemma(self):
        entities = [{"text": "Bosfor", "label": "geogName"}]
        assert aggregate_entities(entities) == {("geogName", "Bosfor"): 1}

    def test_filters_unwanted_types(self):
        entities = [
            {"text": "NATO", "label": "orgName", "lemma": "NATO"},
            {"text": "wtorek", "label": "date", "lemma": "wtorek"},
            {"text": "Warszawa", "label": "placeName", "lemma": "Warszawa"},
        ]
        assert aggregate_entities(entities) == {("placeName", "Warszawa"): 1}

    def test_default_types_cover_persons_and_places(self):
        assert ENTITY_TYPES == ("persName", "geogName", "placeName")

    def test_skips_blank_entities(self):
        assert aggregate_entities([{"text": "  ", "label": "persName"}]) == {}

    def test_skips_lowercase_mentions(self):
        """Przymiotniki ('ukraiński') błędnie oznaczane jako placeName — odpadają po wielkości litery."""
        entities = [
            {"text": "ukraiński", "label": "placeName", "lemma": "ukraiński", "pos": "ADJ"},
            {"text": "Ukraina", "label": "placeName", "lemma": "Ukraina"},
        ]
        assert aggregate_entities(entities) == {("placeName", "Ukraina"): 1}

    def test_lowercase_lemma_of_capitalized_mention_is_kept(self):
        """Lemat może zaczynać się małą literą ('cieśnina Ormuz') — filtr patrzy na tekst wzmianki."""
        entities = [{"text": "Cieśninie Ormuz", "label": "geogName", "lemma": "cieśnina Ormuz"}]
        assert aggregate_entities(entities) == {("geogName", "cieśnina Ormuz"): 1}


class TestAggregateEntitiesDetailed:
    def test_collects_distinct_surface_variants_in_seen_order(self):
        entities = [
            {"text": "Kijowie", "label": "placeName", "lemma": "Kijów"},
            {"text": "Kijowa", "label": "placeName", "lemma": "Kijów"},
            {"text": "Kijowa", "label": "placeName", "lemma": "Kijów"},
        ]
        assert aggregate_entities_detailed(entities) == {
            ("placeName", "Kijów"): {
                "count": 3,
                "variants": ["Kijowie", "Kijowa"],
                "raw_lemmas": ["Kijów"],
            },
        }

    def test_counts_match_aggregate_entities(self):
        entities = [
            {"text": "Tuska", "label": "persName", "lemma": "Tusk"},
            {"text": "Tusk", "label": "persName", "lemma": "Tusk"},
            {"text": "ukraiński", "label": "placeName", "lemma": "ukraiński"},
        ]
        detailed = aggregate_entities_detailed(entities)
        assert {k: g["count"] for k, g in detailed.items()} == aggregate_entities(entities)


class TestAggregateNormalization:
    def test_lowercase_legacy_country_forms_are_rejected(self):
        entities = [
            {"text": "Polska", "label": "placeName", "lemma": "Polska"},
            {"text": "polski", "label": "placeName", "lemma": "polski"},
            {"text": "polska", "label": "placeName", "lemma": "polska"},
        ]
        assert aggregate_entities_detailed(entities) == {
            ("placeName", "Polska"): {
                "count": 1,
                "variants": ["Polska"],
                "raw_lemmas": ["Polska"],
            },
        }

    def test_ukraine_case_variants_share_canonical_name(self):
        entities = [
            {"text": "Ukraina", "label": "placeName", "lemma": "Ukraina"},
            {"text": "UKRAINA", "label": "placeName", "lemma": "ukraina"},
        ]
        assert aggregate_entities(entities) == {("placeName", "Ukraina"): 2}

    def test_lowercase_inflected_country_is_rejected_without_pos(self):
        entities = [{"text": "polskiej", "label": "placeName", "lemma": "polski"}]
        assert aggregate_entities(entities) == {}

    def test_person_name_is_never_canonicalized_as_country(self):
        entities = [{"text": "Czechowa", "label": "persName", "lemma": "Czechow", "pos": "PROPN"}]
        assert aggregate_entities(entities) == {("persName", "Czechow"): 1}

    def test_initials_only_are_rejected_but_initial_with_surname_stays(self):
        entities = [
            {"text": "A.", "label": "persName", "lemma": "A."},
            {"text": "J. K.", "label": "persName", "lemma": "J. K."},
            {"text": "J. Kowalski", "label": "persName", "lemma": "J. Kowalski"},
        ]
        assert aggregate_entities(entities) == {("persName", "J. Kowalski"): 1}

    def test_curated_demonym_maps_to_country(self):
        entities = [{"text": "Turcy", "label": "placeName", "lemma": "Turk", "pos": "NOUN"}]
        assert aggregate_entities(entities) == {("placeName", "Turcja"): 1}

    def test_kurds_are_not_mapped_to_a_country(self):
        entities = [{"text": "Kurdowie", "label": "placeName", "lemma": "Kurd", "pos": "NOUN"}]
        assert aggregate_entities(entities) == {("placeName", "Kurdowie"): 1}

    def test_truncated_lemma_falls_back_to_full_surface(self):
        entities = [{"text": "Brnem", "label": "placeName", "lemma": "Brn", "pos": "PROPN"}]
        assert aggregate_entities(entities) == {("placeName", "Brnem"): 1}

    def test_uppercase_country_abbreviation_maps_to_country(self):
        entities = [{"text": "PL", "label": "geogName", "lemma": "PL", "pos": "PROPN"}]
        assert aggregate_entities(entities) == {("geogName", "Polska"): 1}

    def test_mixed_case_country_abbreviation_is_not_mapped(self):
        entities = [{"text": "Pl", "label": "geogName", "lemma": "Pl", "pos": "PROPN"}]
        assert aggregate_entities(entities) == {("geogName", "Pl"): 1}

    def test_common_noun_dana_is_rejected_with_pos(self):
        entities = [{"text": "Dana", "label": "persName", "lemma": "Dan", "pos": "NOUN"}]
        assert aggregate_entities(entities) == {}

    def test_dana_is_rejected_when_spacy_marks_it_as_proper_noun(self):
        entities = [{"text": "Dana", "label": "persName", "lemma": "Dan", "pos": "PROPN"}]
        assert aggregate_entities(entities) == {}

    def test_dana_is_kept_without_pos_for_legacy_service(self):
        entities = [{"text": "Dana", "label": "persName", "lemma": "Dan"}]
        assert aggregate_entities(entities) == {("persName", "Dan"): 1}

    def test_non_nominal_root_is_rejected(self):
        entities = [{"text": "Polski", "label": "placeName", "lemma": "polski", "pos": "ADJ"}]
        assert aggregate_entities(entities) == {}

    def test_place_labels_merge_and_more_frequent_label_wins(self):
        entities = [
            {"text": "Ukraina", "label": "geogName", "lemma": "Ukraina"},
            {"text": "Ukraina", "label": "placeName", "lemma": "Ukraina"},
            {"text": "UKRAINA", "label": "placeName", "lemma": "ukraina"},
        ]
        assert aggregate_entities(entities) == {("placeName", "Ukraina"): 3}

    def test_unicode_is_normalized_to_nfc_before_grouping(self):
        entities = [
            {"text": "Łódź", "label": "placeName", "lemma": "Łódź"},
            {"text": "Ło\u0301dź", "label": "placeName", "lemma": "Ło\u0301dź"},
        ]
        assert aggregate_entities(entities) == {("placeName", "Łódź"): 2}
