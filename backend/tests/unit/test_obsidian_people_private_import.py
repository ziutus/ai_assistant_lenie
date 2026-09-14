"""Synthetic data only: no NAS connection, scratch manifest, or vault access."""

import datetime
from unittest.mock import MagicMock

import pytest

from imports.obsidian_people_private_import import (
    MARKER, append_private, names_for, route_fields, route_operation, run_import,
)
from library.db.models import Contact, ContactCategory, ContactGroup


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
