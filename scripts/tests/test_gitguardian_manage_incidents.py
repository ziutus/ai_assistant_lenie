"""Unit tests for gitguardian_manage_incidents helpers."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from gitguardian_manage_incidents import _incident_matches_repo


class TestIncidentMatchesRepo:
    def test_matches_exact_name(self):
        inc = {"occurrences": [{"source": {"display_name": "lenie-server-2025"}}]}
        assert _incident_matches_repo(inc, "lenie-server-2025") is True

    def test_matches_substring(self):
        inc = {"occurrences": [{"source": {"display_name": "lenie-server-2025"}}]}
        assert _incident_matches_repo(inc, "lenie") is True

    def test_case_insensitive(self):
        inc = {"occurrences": [{"source": {"display_name": "Lenie-Server-2025"}}]}
        assert _incident_matches_repo(inc, "lenie-server") is True

    def test_no_match(self):
        inc = {"occurrences": [{"source": {"display_name": "other-repo"}}]}
        assert _incident_matches_repo(inc, "lenie") is False

    def test_empty_occurrences(self):
        inc = {"occurrences": []}
        assert _incident_matches_repo(inc, "lenie") is False

    def test_none_occurrences(self):
        inc = {}
        assert _incident_matches_repo(inc, "lenie") is False

    def test_missing_source(self):
        inc = {"occurrences": [{}]}
        assert _incident_matches_repo(inc, "lenie") is False

    def test_missing_display_name(self):
        inc = {"occurrences": [{"source": {}}]}
        assert _incident_matches_repo(inc, "lenie") is False

    def test_multiple_occurrences_one_matches(self):
        inc = {
            "occurrences": [
                {"source": {"display_name": "other-repo"}},
                {"source": {"display_name": "lenie-server-2025"}},
            ]
        }
        assert _incident_matches_repo(inc, "lenie") is True

    def test_source_is_none(self):
        inc = {"occurrences": [{"source": None}]}
        assert _incident_matches_repo(inc, "lenie") is False
