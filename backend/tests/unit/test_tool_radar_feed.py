from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

pytest.importorskip("sqlalchemy")

from library import feed_mentions, tool_radar_feed, tool_relations_service as relations


class TestSuggestName:
    @pytest.mark.parametrize("title,expected", [
        ("Floci - testuj aplikacje chmurowe lokalnie (AWS/Azure/OCl)", "Floci"),
        ("Jevgrep – lepsze wyszukiwanie kontekstu", "Jevgrep"),
        ("Terraform: infrastruktura jako kod", "Terraform"),
        ("Tool | Blog", "Tool"),
        ("Samo-tytul bez separatora", "Samo-tytul bez separatora"),
    ])
    def test_name_is_the_part_before_the_first_separator(self, title, expected):
        assert tool_radar_feed.suggest_name(title) == expected


def _feed_item(**extra):
    base = dict(id=12193, title="Floci - emulator AWS", summary="Local AWS emulator", url="https://floci.io/",
                feed_source_id=1, document_id=None)
    base.update(extra)
    return SimpleNamespace(**base)


class TestSendToRadar:
    def _session(self, item, existing_recommendation=None, existing_tool=None):
        session = MagicMock()
        session.get.side_effect = lambda model, key: item if model.__name__ == "FeedItem" else SimpleNamespace(name="Techmeme")
        lookups = iter([existing_recommendation, existing_tool])
        session.execute.return_value.scalars.return_value.first.side_effect = lambda: next(lookups)
        session.execute.return_value.first.return_value = None  # no evidence yet
        return session

    def test_new_tool_is_added_with_provenance_and_the_feed_item_leaves_the_queue(self, monkeypatch):
        item = _feed_item()
        session = self._session(item)
        transition = MagicMock()
        monkeypatch.setattr(tool_radar_feed, "transition_item", transition)
        monkeypatch.setattr(relations, "detect_relations", lambda _s, _r: {"created": ["AWS"], "existing": 0})

        outcome = tool_radar_feed.send_to_radar(session, 12193, 7, name="Floci", category="Development")

        added = [call.args[0] for call in session.add.call_args_list]
        recommendation = next(a for a in added if a.__class__.__name__ == "ToolRecommendation")
        evidence = next(a for a in added if a.__class__.__name__ == "ToolRecommendationEvidence")
        assert (recommendation.name, recommendation.status, recommendation.category) == ("Floci", "watchlist", "Development")
        assert recommendation.source_url == "https://floci.io/" and recommendation.source_context == "Feed: Techmeme"
        assert evidence.relation_type == "mentioned_in" and evidence.catalog_url == "https://floci.io/"
        transition.assert_called_once_with(session, 12193, "skipped", 7, "sent_to_radar")
        assert outcome["created"] is True and outcome["proposed_relations"] == ["AWS"]

    def test_existing_radar_entry_only_gets_new_evidence(self, monkeypatch):
        item = _feed_item(id=563, url="https://github.com/hectorvent/floci")
        existing = SimpleNamespace(id=5, name="Floci")
        session = self._session(item, existing_recommendation=existing)
        monkeypatch.setattr(tool_radar_feed, "transition_item", MagicMock())

        outcome = tool_radar_feed.send_to_radar(session, 563, 7, name="Floci", homepage_url="")

        added = [call.args[0].__class__.__name__ for call in session.add.call_args_list]
        assert added == ["ToolRecommendationEvidence"]
        assert outcome["created"] is False and outcome["evidence_added"] is True

    def test_failed_transition_rolls_everything_back(self, monkeypatch):
        session = self._session(_feed_item())
        monkeypatch.setattr(tool_radar_feed, "transition_item", MagicMock(side_effect=RuntimeError("invalid feed item state transition")))
        monkeypatch.setattr(relations, "detect_relations", lambda _s, _r: {"created": [], "existing": 0})

        with pytest.raises(RuntimeError):
            tool_radar_feed.send_to_radar(session, 12193, 7, name="Floci")

        session.rollback.assert_called_once()

    def test_unknown_item_and_empty_name_are_rejected(self):
        session = MagicMock()
        session.get.return_value = None
        with pytest.raises(ValueError, match="not found"):
            tool_radar_feed.send_to_radar(session, 1, 7)
        session.get.return_value = _feed_item(title="   ")
        with pytest.raises(ValueError, match="name is required"):
            tool_radar_feed.send_to_radar(session, 1, 7)


class TestPolishInflectionAndAlternatives:
    def test_inflected_names_match(self):
        assert relations.name_pattern("Jev").search("konkurent Jeva")
        assert relations.name_pattern("Terraform").search("z Terraformem")
        assert not relations.name_pattern("Terraform").search("terraformer")

    def test_wording_next_to_the_name_makes_it_an_alternative(self):
        item = SimpleNamespace(id=9, name="Clef", description="Cloudflare Clef - otwartoźródłowy konkurent Jeva",
                               source_context=None, source_document_id=None)
        session = MagicMock()
        others = MagicMock()
        others.scalars.return_value.all.return_value = [SimpleNamespace(id=2, name="Jev", status="watchlist")]
        none = MagicMock()
        none.scalars.return_value.first.return_value = None
        session.execute.side_effect = [others, none]

        outcome = relations.detect_relations(session, item)

        assert outcome["created"] == ["Jev"]
        assert session.add.call_args.args[0].relation == "alternative_to"


class TestOnePerName:
    def test_duplicate_names_collapse_to_the_adopted_or_lowest_id_entry(self):
        entries = [SimpleNamespace(id=8, name="Gemini", status="watchlist"), SimpleNamespace(id=3, name="gemini", status="watchlist"),
                   SimpleNamespace(id=9, name="Gemini", status="adopted"), SimpleNamespace(id=4, name="AWS", status="adopted")]
        assert sorted(e.id for e in relations._one_per_name(entries)) == [4, 9]
        entries[2].status = "watchlist"
        assert sorted(e.id for e in relations._one_per_name(entries)) == [3, 4]


class TestFeedMentions:
    def test_counts_inflected_whole_word_mentions_with_samples(self, monkeypatch):
        feed_mentions.reset_cache()
        session = MagicMock()
        session.execute.return_value.all.return_value = [
            (1, "Jev - AI do decyzji", "model", "https://a"),
            (2, "Clef: konkurent Jeva", None, "https://b"),
            (3, "Jevgrep - wyszukiwanie", None, "https://c"),
            (4, "Nic o tym", "AWS i GCP", "https://d"),
        ]

        result = feed_mentions.mentions_for(session, {10: "Jev", 11: "AWS", 12: "Nieistniejace"})

        assert result[10]["count"] == 2  # Jev and Jeva, not Jevgrep
        assert [s["id"] for s in result[10]["samples"]] == [1, 2]
        assert result[11]["count"] == 1
        assert 12 not in result
        feed_mentions.reset_cache()
