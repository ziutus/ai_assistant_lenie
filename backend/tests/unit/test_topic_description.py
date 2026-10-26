import json
from unittest.mock import MagicMock

import pytest

from library import content_group_service as groups
from library import content_group_suggestion_service as suggestions
from library.db.models import ContentGroup


def test_description_is_trimmed_and_blank_becomes_none():
    assert groups.validate_description("  Kradzież   tożsamości \n i PESEL ", "topic") == "Kradzież tożsamości i PESEL"
    assert groups.validate_description("   ", "topic") is None
    assert groups.validate_description(None, "topic") is None


@pytest.mark.parametrize("value,kind,message", [
    (5, "topic", "description must be a string"),
    ("x" * 301, "topic", "at most 300 characters"),
    ("opis", "priority", "only topics have a description"),
])
def test_invalid_description(value, kind, message):
    with pytest.raises(ValueError, match=message):
        groups.validate_description(value, kind)


def test_update_group_sets_and_clears_description():
    session = MagicMock()
    session.scalars.return_value.all.return_value = []
    group = ContentGroup(id=1, name="OpSec", kind="topic", parent_id=None, archived_at=None)
    groups.update_group(session, group, description="Bezpieczeństwo danych osobowych")
    assert group.description == "Bezpieczeństwo danych osobowych"
    groups.update_group(session, group, name="OpSec i ochrona danych")
    assert group.description == "Bezpieczeństwo danych osobowych"  # absent key = unchanged
    groups.update_group(session, group, description="")
    assert group.description is None


def test_group_to_dict_returns_description():
    group = ContentGroup(id=1, name="OpSec", kind="topic", description="opis")
    assert groups.group_to_dict(group)["description"] == "opis"


def test_catalog_carries_description_only_when_set():
    rows = [ContentGroup(id=1, name="A", kind="topic"), ContentGroup(id=2, name="B", kind="topic", description="o B")]
    session = MagicMock()
    session.scalars.return_value.all.return_value = rows
    catalog = suggestions.active_topic_catalog(session)
    assert catalog == [{"id": 1, "name": "A"}, {"id": 2, "name": "B", "description": "o B"}]
    # a catalog without descriptions serialises exactly as before, so old prompt hashes stay valid
    assert json.dumps(catalog[:1], ensure_ascii=False) == '[{"id": 1, "name": "A"}]'
