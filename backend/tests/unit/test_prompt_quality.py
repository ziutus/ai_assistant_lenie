from types import SimpleNamespace

from library.prompt_template_routes import build_quality


def run(run_id, item_id, raw, suggestions=()):
    return SimpleNamespace(
        id=run_id, feed_item_id=item_id, raw_result=raw, model="m", prompt_version="feed_item-v2",
        suggestions=[SimpleNamespace(group_id=group_id, status=status) for group_id, status in suggestions],
    )


TOPICS = {1: "AI", 2: "OpSec i ochrona danych", 3: "Podróże"}
ITEMS = {10: SimpleNamespace(title="Polisa na cudze dane"), 11: SimpleNamespace(title="Nowy model")}


def test_miss_is_a_run_without_suggestions_that_the_reader_filed_by_hand():
    runs = [run(5, 10, {
        "no_match": True, "suggestions": [], "new_topics": [{"name": "Ochrona danych osobowych", "confidence": 0.9}],
        "dropped_new_topics": [{"name": "OpSec i ochrona danych", "confidence": 0.8, "dropped_because": "duplicate_of_catalog"}],
    })]
    result = build_quality(runs, ITEMS, {10: [2]}, TOPICS)
    assert result["missed_by_model"] == [{
        "feed_item_id": 10, "title": "Polisa na cudze dane", "run_id": 5, "model": "m", "prompt_version": "feed_item-v2",
        "no_match": True, "new_topics": ["Ochrona danych osobowych"],
        "dropped_new_topics": [{"name": "OpSec i ochrona danych", "confidence": 0.8, "dropped_because": "duplicate_of_catalog"}],
        "filed_under": ["OpSec i ochrona danych"],
    }]


def test_no_miss_when_the_model_suggested_something_or_the_reader_filed_nothing():
    runs = [run(5, 10, {"suggestions": []}, suggestions=[(1, "dismissed")]), run(6, 11, {"no_match": True, "suggestions": []})]
    assert build_quality(runs, ITEMS, {10: [2]}, TOPICS)["missed_by_model"] == []


def test_only_the_latest_run_of_an_item_counts():
    runs = [run(9, 10, {"suggestions": []}, suggestions=[(1, "accepted")]), run(5, 10, {"no_match": True, "suggestions": []})]
    result = build_quality(runs, ITEMS, {10: [2]}, TOPICS)
    assert result["items_considered"] == 1
    assert result["missed_by_model"] == []


def test_new_topic_proposals_are_grouped_ignoring_case_and_diacritics():
    runs = [
        run(5, 10, {"new_topics": [{"name": "Ochrona danych", "confidence": 0.9}]}),
        run(6, 11, {"new_topics": [{"name": "ochrona  DANYCH", "confidence": 0.7}, {"name": "", "confidence": 1}]}),
    ]
    proposals = build_quality(runs, ITEMS, {}, TOPICS)["new_topic_proposals"]
    assert proposals == [{"name": "Ochrona danych", "count": 2, "avg_confidence": 0.8, "feed_item_ids": [10, 11]}]


def test_runs_that_succeeded_only_after_a_retry_are_listed_with_the_earlier_error():
    runs = [run(5, 10, {"suggestions": [], "retried_after": "Error code: 429 " + "x" * 300, "attempts": 3}), run(6, 11, {"suggestions": []})]
    result = build_quality(runs, ITEMS, {}, TOPICS)
    assert result["retried_runs"] == [{"run_id": 5, "feed_item_id": 10, "model": "m", "attempts": 3, "error": ("Error code: 429 " + "x" * 300)[:200]}]


def test_per_topic_counts_show_topics_that_are_never_suggested_first():
    runs = [run(5, 10, {}, suggestions=[(1, "accepted"), (1, "dismissed")])]
    per_topic = build_quality(runs, ITEMS, {}, TOPICS)["per_topic"]
    assert [entry["name"] for entry in per_topic] == ["OpSec i ochrona danych", "Podróże", "AI"]
    assert per_topic[-1] == {"group_id": 1, "name": "AI", "suggested": 2, "accepted": 1, "dismissed": 1}
