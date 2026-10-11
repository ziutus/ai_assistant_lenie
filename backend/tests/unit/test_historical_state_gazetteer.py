"""Unit tests for library.historical_state_gazetteer and its wiring into
ner_client (canonical name) and place_verification (synthetic resolved row)."""

import os
import sys
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from library import historical_state_gazetteer  # noqa: E402
from library.db.models import GeocodeCache  # noqa: E402
from library.ner_client import aggregate_entities  # noqa: E402
from library.place_verification import _get_or_create_geocode  # noqa: E402


class TestCanonicalHistoricalStateName:
    @pytest.mark.parametrize("mention", ["Jugosławia", "Jugosławii", "Jugosławię", "Jugosławią"])
    def test_jugoslavia_inflections(self, mention):
        assert historical_state_gazetteer.canonical_historical_state_name(mention) == "Jugosławia"

    @pytest.mark.parametrize("mention", ["ZSRR", "Związek Radziecki", "Związku Radzieckiego", "Związkiem Radzieckim"])
    def test_soviet_union(self, mention):
        assert historical_state_gazetteer.canonical_historical_state_name(mention) == "Związek Radziecki"

    def test_others(self):
        assert historical_state_gazetteer.canonical_historical_state_name("Czechosłowacji") == "Czechosłowacja"
        assert historical_state_gazetteer.canonical_historical_state_name("NRD") == "NRD"
        assert historical_state_gazetteer.canonical_historical_state_name("Prusach") == "Prusy"

    @pytest.mark.parametrize(
        "mention",
        ["Birmingham", "Prus", "Prusy Wschodnie", "Sowieci", "Serbia", "Warszawa", "Jugosławia i Serbia", "   ", ""],
    )
    def test_non_matches(self, mention):
        assert historical_state_gazetteer.canonical_historical_state_name(mention) is None


class TestHistoricalStateLookup:
    def test_exact_lookup_has_period(self):
        state = historical_state_gazetteer.historical_state("Jugosławia")
        assert state is not None
        assert (state.year_from, state.year_to) == (1918, 2006)
        assert state.info()["successors"]

    def test_lookup_is_exact(self):
        assert historical_state_gazetteer.historical_state("Jugosławii") is None
        assert historical_state_gazetteer.historical_state("Warszawa") is None


class TestNerCanonicalization:
    def test_inflected_label_collapses_to_canonical(self):
        entities = [{"text": "Jugosławii", "label": "placeName", "lemma": "Jugosławii"}]
        assert aggregate_entities(entities) == {("placeName", "Jugosławia"): 1}

    def test_truncated_manual_style_form_is_not_invented(self):
        entities = [{"text": "Jugosławi", "label": "placeName", "lemma": "Jugosławi"}]
        # "jugoslawi*" stem covers the truncated form too - it resolves rather than staying a typo.
        assert aggregate_entities(entities) == {("placeName", "Jugosławia"): 1}


class TestGetOrCreateGeocodeHistoricalState:
    def _session(self, existing=None):
        session = MagicMock()
        session.query.return_value.filter.return_value.one_or_none.return_value = existing
        return session

    def test_resolves_without_calling_geocoder(self):
        session = self._session()
        with patch("library.place_verification.geocode") as mock_geocode:
            row = _get_or_create_geocode(session, "Jugosławia")

        mock_geocode.assert_not_called()
        assert row.resolved is True
        assert row.display_name == "Jugosławia"
        assert row.osm_type == "historical_state"
        assert row.raw["historical"]["year_from"] == 1918
        assert row.raw["historical"]["year_to"] == 2006

    def test_upgrades_negative_cache_entry(self):
        stale = MagicMock(spec=GeocodeCache)
        stale.resolved = False
        stale.display_name = None
        session = self._session(existing=stale)

        row = _get_or_create_geocode(session, "Jugosławia")

        assert row is stale
        assert row.resolved is True
        assert row.osm_type == "historical_state"
