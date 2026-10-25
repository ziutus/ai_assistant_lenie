"""Deleting an organization nothing depends on (orphans 1152 / 1188 left after doc #10872 fixes)."""

from unittest.mock import MagicMock

import pytest

pytest.importorskip("sqlalchemy")

from library.db.models import Organization  # noqa: E402
from library.organization_registry import OrganizationInUseError, delete_unused_organization  # noqa: E402


def scalar_result(value):
    result = MagicMock()
    result.scalar.return_value = value
    return result


def source_result(source_id):
    result = MagicMock()
    result.scalars.return_value.first.return_value = source_id
    return result


def session_with(documents=0, source_id=None, aliases=0, countries=0, ambiguous=0):
    session = MagicMock()
    session.execute.side_effect = [
        scalar_result(documents), source_result(source_id),
        scalar_result(aliases), scalar_result(countries), scalar_result(ambiguous),
    ]
    return session


def test_unused_organization_is_deleted_and_removed_counts_are_reported():
    organization = Organization(id=1152, canonical_name="Departamentu Obrony na Departament Wojny")
    session = session_with(aliases=2, countries=1, ambiguous=0)

    assert delete_unused_organization(session, organization) == {"aliases": 2, "countries": 1, "ambiguous_aliases": 0}
    session.delete.assert_called_once_with(organization)


@pytest.mark.parametrize("kwargs,expected_counts", [
    ({"documents": 3}, {"documents": 3}),
    ({"source_id": 200}, {"information_source_id": 200}),
])
def test_organization_in_use_is_refused_without_deleting(kwargs, expected_counts):
    organization = Organization(id=9, canonical_name="NATO")
    session = session_with(**kwargs)

    with pytest.raises(OrganizationInUseError) as error:
        delete_unused_organization(session, organization)
    assert error.value.counts == expected_counts
    session.delete.assert_not_called()


def test_country_organization_is_never_deleted():
    organization = Organization(id=5, canonical_name="Polska", organization_type="country")
    session = MagicMock()

    with pytest.raises(OrganizationInUseError, match="państwo"):
        delete_unused_organization(session, organization)
    session.execute.assert_not_called()
    session.delete.assert_not_called()
