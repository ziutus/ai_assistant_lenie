"""Renaming an organization together with its entities and information source."""

from unittest.mock import MagicMock

import pytest

pytest.importorskip("sqlalchemy")

from library import organization_registry  # noqa: E402
from library import organization_source_sync as sync  # noqa: E402
from library.db.models import (  # noqa: E402
    DocumentEntity,
    DocumentInformationSource,
    InformationSource,
    InformationSourceAlias,
    Organization,
)


class FakeSession:
    """Answers scalar()/scalars() from queues, in the order the code asks."""

    def __init__(self, scalar=(), scalars=()):
        self._scalar, self._scalars = list(scalar), list(scalars)
        self.added, self.deleted = [], []

    def scalar(self, _stmt):
        return self._scalar.pop(0)

    def scalars(self, _stmt):
        return MagicMock(all=lambda rows=self._scalars.pop(0): rows)

    def add(self, obj):
        self.added.append(obj)

    def delete(self, obj):
        self.deleted.append(obj)

    def flush(self):
        pass


@pytest.fixture()
def fake_rename(monkeypatch):
    def rename(session, organization, new_name):
        organization.canonical_name = new_name
        return organization

    monkeypatch.setattr(organization_registry, "rename", rename)


def org(name="telegrapha"):
    return Organization(id=842, canonical_name=name)


def entity(text="telegrapha", document_id=10753):
    return DocumentEntity(id=1, document_id=document_id, entity_type="orgName", entity_text=text, variants=[])


@pytest.mark.parametrize("raw, expected", [
    ("https://www.telegraph.co.uk/", "telegraph.co.uk"),
    ("http://Telegraph.co.uk/news?x=1#top", "telegraph.co.uk"),
    ("www.bbc.com", "bbc.com"),
    ("user@bbc.co.uk:8080/path", "bbc.co.uk"),
    ("  ", None),
    (None, None),
])
def test_normalize_domain(raw, expected):
    assert sync.normalize_domain(raw) == expected


@pytest.mark.parametrize("raw", ["not a domain", "localhost", "http://", "a..b.com", "-bad.com"])
def test_normalize_domain_rejects_garbage(raw):
    with pytest.raises(ValueError):
        sync.normalize_domain(raw)


def test_update_source_details_normalizes_and_shares_description_with_organization():
    organization = org("The Telegraph")
    source = InformationSource(id=75, canonical_name="The Telegraph", organization_id=842)
    session = MagicMock()
    session.get.return_value = organization

    sync.update_source_details(session, source, {
        "source_type": " newspaper ", "domain": "https://www.telegraph.co.uk/",
        "description": "Brytyjski dziennik, założony w 1855.",
    })

    assert (source.source_type, source.domain) == ("newspaper", "telegraph.co.uk")
    assert source.description == organization.description == "Brytyjski dziennik, założony w 1855."


def test_update_source_details_clears_fields_and_validates_length():
    source = InformationSource(id=1, canonical_name="X", source_type="portal", domain="x.com", description="d")
    session = MagicMock()

    sync.update_source_details(session, source, {"source_type": "", "domain": "", "description": ""})
    assert (source.source_type, source.domain, source.description) == (None, None, None)

    with pytest.raises(ValueError):
        sync.update_source_details(session, source, {"source_type": "x" * 31})
    with pytest.raises(ValueError):
        sync.update_source_details(session, source, {"description": "x" * 2001})
    with pytest.raises(ValueError):
        sync.update_source_details(session, source, {"domain": "no spaces allowed"})


def test_rename_with_unique_name_renames_entity_and_source_and_keeps_old_names(fake_rename):
    organization, row = org(), entity()
    source = InformationSource(id=200, canonical_name="telegrapha", organization_id=842)
    session = FakeSession(scalar=[None, source, None], scalars=[[row]])

    result = sync.rename_organization(session, organization, "The Telegraph")

    assert (row.entity_text, row.variants) == ("The Telegraph", ["telegrapha"])
    assert source.canonical_name == "The Telegraph"
    assert [alias.alias for alias in source.aliases] == ["telegrapha"]
    assert result["entities_renamed"] == 1 and result["source"]["action"] == "renamed"


def test_rename_merges_into_existing_source_with_the_corrected_name(fake_rename):
    """The reported case: lemma-named source #200 vs. the proper-name source #75."""
    organization, row = org(), entity()
    lemma = InformationSource(id=200, canonical_name="telegrapha", source_type="organization", organization_id=842)
    proper = InformationSource(id=75, canonical_name="The Telegraph", source_type="newspaper", domain="telegraph.co.uk")
    InformationSourceAlias(source=proper, alias='gazecie "The Telegraph"')
    link = DocumentInformationSource(id=448, document_id=10753, source_id=200, role="cited", raw_mention="Telegrapha")
    session = FakeSession(scalar=[None, lemma, proper, None], scalars=[[row], [link]])

    result = sync.rename_organization(session, organization, "The Telegraph")

    assert result["source"] == {"action": "merged", "source_id": 75, "merged_source_id": 200}
    assert link.source_id == 75
    assert session.deleted == [lemma]
    assert proper.organization_id == 842 and lemma.organization_id is None
    assert (proper.source_type, proper.domain) == ("newspaper", "telegraph.co.uk")  # target's own data wins
    assert sorted(alias.alias for alias in proper.aliases) == ['gazecie "The Telegraph"', "telegrapha"]


def test_merge_drops_a_link_the_target_already_has_in_that_document(fake_rename):
    organization, row = org(), entity()
    lemma = InformationSource(id=200, canonical_name="telegrapha", organization_id=842)
    proper = InformationSource(id=75, canonical_name="The Telegraph")
    link = DocumentInformationSource(id=448, document_id=10753, source_id=200, role="cited", raw_mention="Telegrapha")
    session = FakeSession(scalar=[None, lemma, proper, 999], scalars=[[row], [link]])

    sync.rename_organization(session, organization, "The Telegraph")

    assert link in session.deleted and link.source_id == 200


def test_merge_fills_only_empty_fields_of_the_target(fake_rename):
    organization = org()
    lemma = InformationSource(id=200, canonical_name="telegrapha", source_type="organization",
                              domain="telegraph.co.uk", description="opis", organization_id=842)
    proper = InformationSource(id=75, canonical_name="The Telegraph", source_type=None)
    session = FakeSession(scalar=[lemma, proper], scalars=[[], []])

    sync.rename_organization(session, organization, "The Telegraph")

    assert (proper.source_type, proper.domain, proper.description) == ("organization", "telegraph.co.uk", "opis")


def test_rename_binds_an_unbound_same_named_source_when_the_organization_has_none(fake_rename):
    organization = org()
    proper = InformationSource(id=75, canonical_name="The Telegraph")
    session = FakeSession(scalar=[None, proper], scalars=[[]])

    result = sync.rename_organization(session, organization, "The Telegraph")

    assert result["source"] == {"action": "bound", "source_id": 75}
    assert proper.organization_id == 842


def test_rename_without_any_source_only_renames_entities(fake_rename):
    session = FakeSession(scalar=[None, None], scalars=[[]])

    result = sync.rename_organization(session, org(), "The Telegraph")

    assert result["source"] == {"action": "none"}


def test_rename_refuses_a_source_that_belongs_to_another_organization(fake_rename):
    lemma = InformationSource(id=200, canonical_name="telegrapha", organization_id=842)
    other = InformationSource(id=75, canonical_name="The Telegraph", organization_id=7)
    session = FakeSession(scalar=[lemma, other], scalars=[[]])

    with pytest.raises(sync.SourceConflictError):
        sync.rename_organization(session, org(), "The Telegraph")


def test_entity_name_clash_in_a_document_is_counted_and_left_alone(fake_rename):
    row = entity()
    session = FakeSession(scalar=[555, None, None], scalars=[[row]])

    result = sync.rename_organization(session, org(), "The Telegraph")

    assert row.entity_text == "telegrapha"
    assert result["entity_conflicts"] == 1 and result["entities_renamed"] == 0


def test_same_name_is_a_noop(monkeypatch):
    monkeypatch.setattr(organization_registry, "rename", lambda session, organization, name: organization)
    session = FakeSession()

    result = sync.rename_organization(session, org("The Telegraph"), "The Telegraph")

    assert result["source"] == {"action": "none"} and result["entities_renamed"] == 0
