"""Model choice for topic suggestions: allowlist validation and the per-task model list."""

import pytest

pytest.importorskip("sqlalchemy")

import library.content_group_suggestion_service as svc  # noqa: E402
from library.llm_model_registry import is_selectable  # noqa: E402


def test_request_suggestions_rejects_model_outside_allowlist():
    with pytest.raises(ValueError, match="not allowed"):
        svc.request_suggestions(object(), "feed_item", 1, model="some/arbitrary-model")


def test_registry_offers_the_default_model_for_topic_suggestions():
    assert is_selectable("Bielik-11B-v3.0-Instruct", svc.SUGGESTION_TASK)
    assert not is_selectable("some/arbitrary-model", svc.SUGGESTION_TASK)
