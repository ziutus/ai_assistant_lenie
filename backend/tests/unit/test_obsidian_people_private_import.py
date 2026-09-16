"""Synthetic data only: no NAS connection, scratch manifest, or vault access."""

import datetime
from unittest.mock import MagicMock

import pytest

from imports.obsidian_people_private_import import (
    MARKER, append_private, names_for, route_fields, route_operation, run_import,
)
from library.db.models import Contact, ContactCategory, ContactChangeLog, ContactGroup, ContactLink


def test_routing_and_multi_names_keep_narrative_private():
    fields, private, flags = route_fields(
        "Telefon: +48 123 456 789\nEmail: example@example.invalid\n"
        "LinkedIn: https://www.linkedin.com/in/example\nUrodziny: 1990-02-03\n"
        "Firma: Example Ltd\nNIP: 1234567890\nStanowisko: Tester\nAdres: Example Street 1\n"
        "Synthetic personal context."
    )
    assert fields == {
        "phone_number": "+48 123 456 789", "email": "example@example.invalid",
        "linkedin_url": "https://www.linkedin.com/in/example", "birthday": datetime.date(1990, 2, 3),
        "company": "Example Ltd; NIP: 1234567890", "position": "Tester", "address": "Example Street 1",
    }
    assert private == "Synthetic personal context."
    assert not flags
    assert "notes" not in fields
    appended = append_private("Earlier synthetic text", private)
    assert appended == f"Earlier synthetic text\n\n{MARKER}\n{private}"
    assert append_private(appended, private) == appended
    assert names_for({"action": "new_contact_multi", "people": ["Example", "Sample"]}) == [
        ("Example", None), ("Sample", None),
    ]
    fields, private, flags = route_fields("Urodziny: 7 grudnia")
    assert not fields  # Do not invent a birth year for the database's Date column.
    assert private
    assert flags == ["BIRTHDAY_UNREPRESENTABLE_WITHOUT_CONFIRMED_DATE"]
    fields, _, flags = route_fields("Urodziny, 3 lutego 1990\n[profile](https://www.linkedin.com/in/example)")
    assert fields["birthday"] == datetime.date(1990, 2, 3)
    assert fields["linkedin_url"] == "https://www.linkedin.com/in/example"
    assert not flags
    _, _, _, per_person = route_operation(
        {"action": "new_contact_multi", "people": ["Example", "Other"]},
        "Example pracuje w ExampleCorp w ExampleCity.\nOther pracuje jako tester w ExampleCity.",
    )
    assert per_person == {"Example": {"company": "ExampleCorp"}, "Other": {"position": "tester"}}


@pytest.mark.parametrize("last_name", ["Person", "WrongIdentity"])
def test_dry_run_never_writes_or_commits(capsys, last_name):
    session = MagicMock()
    group = ContactGroup(id=9, name="Existing group")
    contact = Contact(id=1001, first_name="Example", last_name=last_name, category_id=1,
                      private_notes="Earlier synthetic text", groups=[])

    def scalars(statement):
        entity = statement.column_descriptions[0]["entity"]
        rows = []
        if entity is ContactCategory:
            rows = [ContactCategory(id=1, name="Osoba prywatna")]
        elif entity is Contact:
            rows = [contact]
        elif entity is ContactGroup and 9 in statement.compile().params.values():
            rows = [group]
        result = MagicMock()
        result.__iter__.side_effect = lambda: iter(rows)
        result.one_or_none.return_value = rows[0] if rows else None
        result.first.return_value = rows[0] if rows else None
        return result

    session.scalars.side_effect = scalars
    spec = {
        "groups": {"existing_reused": {"Existing group": 9}, "new_groups_to_create": ["New group"]},
        "operations": [
            {"path": "Example Person.md", "action": "append_existing", "contact_id": 1001,
             "ensure_group": "Existing group"},
            {"path": "Sample.md", "action": "new_contact_multi", "people": ["Sample", "Other"],
             "ensure_group": "New group"},
        ],
    }
    counts = run_import(session, spec, {
        "Example Person.md": ("Email: example@example.invalid\nSynthetic secret A", 1),
        "Sample.md": ("Synthetic secret B", 2),
    })
    assert counts["contacts_to_create"] == 2
    assert counts["append_existing"] == (1 if last_name == "Person" else 0)
    assert counts["id_caveat"] == (0 if last_name == "Person" else 1)
    assert counts["groups_to_create"] == 1
    assert str(session.execute.call_args_list[0].args[0]) == "SET TRANSACTION READ ONLY"
    for method in (session.commit, session.flush, session.add, session.delete):
        method.assert_not_called()
    session.rollback.assert_called_once()
    assert contact.private_notes == "Earlier synthetic text"
    assert contact.email is None
    assert contact.groups == []
    output = capsys.readouterr().out
    assert "Synthetic secret" not in output
    assert "Earlier synthetic text" not in output
    assert "example@example.invalid" not in output
    assert "DRY-RUN" in output


@pytest.mark.parametrize("existing_url", [None, "https://www.linkedin.com/in/old", "https://www.linkedin.com/in/example"])
@pytest.mark.parametrize("apply", [False, True])
@pytest.mark.parametrize("from_secondary", [False, True])
def test_linkedin_is_created_or_updated_in_place(existing_url, apply, from_secondary):
    session = MagicMock()
    contact = Contact(id=1001, first_name="Example", last_name="Person", category_id=1, groups=[])
    secondary = Contact(id=1002, first_name="Example", last_name="Person", category_id=1, groups=[])
    url = "https://www.linkedin.com/in/example"
    existing = ContactLink(id=42, contact_id=1001, link_type="linkedin", url=existing_url) if existing_url else None
    secondary_link = ContactLink(id=43, contact_id=1002, link_type="linkedin", url=url)

    def scalars(statement):
        entity = statement.column_descriptions[0]["entity"]
        params = statement.compile().params.values()
        rows = []
        if entity is ContactCategory:
            rows = [ContactCategory(id=1, name="Osoba prywatna")]
        elif entity is Contact:
            rows = [secondary if 1002 in params else contact]
        elif entity is ContactLink:
            rows = [secondary_link] if 1002 in params else ([existing] if existing else [])
        result = MagicMock()
        result.__iter__.side_effect = lambda: iter(rows)
        result.one_or_none.return_value = rows[0] if rows else None
        return result

    session.scalars.side_effect = scalars
    operation = {"path": "Example Person.md", "action": "append_existing", "contact_id": 1001}
    if from_secondary:
        operation.update(action="merge_duplicates", secondary_contact_id=1002)
    spec = {"groups": {"existing_reused": {}, "new_groups_to_create": []}, "operations": [operation]}
    run_import(session, spec, {"Example Person.md": ("" if from_secondary else f"LinkedIn: {url}", 1)}, apply=apply)
    added_links = [call.args[0] for call in session.add.call_args_list if isinstance(call.args[0], ContactLink)]
    logs = [call.args[0] for call in session.add.call_args_list if isinstance(call.args[0], ContactChangeLog)]
    # A conflicting existing LinkedIn link is always retained (flagged, never overwritten),
    # matching every other field's FIELD_CONFLICT/MERGE_CONFLICT retain behavior.
    changed = existing_url is None
    if not apply:
        session.add.assert_not_called()
        session.flush.assert_not_called()
        session.commit.assert_not_called()
        if existing:
            assert existing.url == existing_url
    elif existing is None:
        assert len(added_links) == 1
        assert added_links[0].contact_id == contact.id
        assert added_links[0].link_type == "linkedin"
        assert added_links[0].url == url
    else:
        assert added_links == []
        assert existing.id == 42
        assert existing.url == (url if changed else existing_url)
    if apply and changed:
        assert len(logs) == 1
        assert logs[0].changed_fields == ["links"]
    else:
        assert logs == []
    assert not hasattr(contact, "linkedin_url")
    assert secondary_link.url == url


def test_linkedin_in_another_persons_narrative_is_not_extracted():
    narrative = "Someone else has profile https://www.linkedin.com/in/someone-else"
    fields, private, _ = route_fields(narrative)
    assert fields == {}
    assert private == narrative
