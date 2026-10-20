"""Replay of manual place decisions after a document's entities were rebuilt."""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

pytest.importorskip("sqlalchemy")

from library.db.models import DocumentEntity  # noqa: E402
from library.entity_overrides import apply_decisions, replay_manual_place_decisions  # noqa: E402


def entity(text, entity_type="placeName", count=1, variants=None, source="ner", geocode_id=None):
    return DocumentEntity(
        id=hash((text, entity_type)) % 100000, document_id=1, entity_type=entity_type, entity_text=text,
        mention_count=count, variants=variants or [], source=source, geocode_id=geocode_id,
    )


def decision(kind, entity_text, entity_type="placeName", **details):
    return SimpleNamespace(decision=kind, entity_text=entity_text, entity_type=entity_type, details=details or None)


def run(decisions, entities):
    session = MagicMock()
    touched, stats = apply_decisions(session, decisions, entities)
    return session, touched, stats


@pytest.mark.parametrize("deleted", [False, True])
def test_confirmed_location_replays_on_new_id_and_later_delete_wins(deleted):
    from library.db.models import GeocodeCache
    row = entity("Huti", variants=["Huty"])
    row.id = 999
    rows = [row]
    session = MagicMock()
    proposal = GeocodeCache(id=17, query="Huti", resolved=True, display_name="Huti, Ukraina", lat=49, lon=24)
    session.get.return_value = proposal
    decisions = [decision("place_confirmed", "Huty", variants=["Huti"], geocode_id=17)]
    if deleted:
        decisions.append(decision("deleted", "Huty"))
    touched, _ = apply_decisions(session, decisions, rows)
    if deleted:
        assert rows == []
        assert touched == {}
    else:
        assert row.id == 999
        assert row.source == "manual"
        assert row.place_verification_status == "confirmed"
        assert row.geocode is proposal
        assert row.geocode_id == 17


def test_confirmed_disappeared_mention_does_not_create_entity():
    session, touched, _ = run([decision("place_confirmed", "Huty", geocode_id=17)], [])
    assert touched == {}
    session.add.assert_not_called()
    session.get.assert_not_called()


def test_confirmed_replay_tags_selected_location_without_geocoding():
    from library.db.models import Document, GeocodeCache
    row = entity("Huty")
    doc = Document(id=1, tags="topic")
    proposal = GeocodeCache(id=17, query="Huty", resolved=True, display_name="Huty, Polska", lat=50, lon=19)
    session = MagicMock()
    session.scalars.return_value.all.side_effect = [[decision("place_confirmed", "Huty", geocode_id=17)], [row]]
    session.get.return_value = proposal
    with patch("library.place_verification.geocode_single_place") as geocode:
        replay_manual_place_decisions(session, 1, doc)
    assert doc.tags == "topic,miejsce-huty"
    assert row.geocode is proposal
    geocode.assert_not_called()


def test_missing_confirmed_cache_row_requires_review_without_lookup():
    row = entity("Huty")
    session = MagicMock()
    session.get.return_value = None
    touched, _ = apply_decisions(session, [decision("place_confirmed", "Huty", geocode_id=17)], [row])
    assert touched == {}
    assert row.place_verification_status == "needs_review"


def test_rejected_proposal_is_replayed_as_unlocated_manual_place():
    row = entity("Huty")
    _, touched, stats = run([decision("place_rejected", "Huty")], [row])
    assert row.place_verification_status == "rejected"
    assert row.source == "manual"
    assert stats["place_rejected"] == 1


def test_place_to_organization_is_replayed_and_drops_the_place_row():
    from library.db.models import DocumentEntity, Organization
    row = entity("Huti", count=3, variants=["Huty"])
    rows = [row]
    session = MagicMock()
    session.scalar.return_value = None
    organization = Organization(id=5, canonical_name="Huti")
    with patch("library.organization_registry.resolve_or_create", return_value=(organization, "canonical_matched")):
        touched, stats = apply_decisions(session, [decision("place_to_organization", "Huti")], rows)
    assert rows == []
    session.delete.assert_called_once_with(row)
    created = next(c.args[0] for c in session.add.call_args_list if isinstance(c.args[0], DocumentEntity))
    assert (created.entity_type, created.entity_text, created.mention_count) == ("orgName", "Huti", 3)
    assert created.variants == ["Huty"]
    assert stats["to_organization"] == 1


def test_person_to_organization_is_replayed_under_the_chosen_name():
    from library.db.models import DocumentEntity, Organization
    row = entity("Xie", entity_type="persName", count=2, variants=["Xie"])
    rows = [row]
    session = MagicMock()
    session.scalar.return_value = None
    organization = Organization(id=7, canonical_name="X")
    with patch("library.organization_registry.resolve_or_create",
               return_value=(organization, "canonical_matched")) as resolve:
        _, stats = apply_decisions(session, [decision("person_to_organization", "Xie", "persName", new_text="X")], rows)
    assert rows == []
    assert resolve.call_args.args[1] == "X"
    created = next(c.args[0] for c in session.add.call_args_list if isinstance(c.args[0], DocumentEntity))
    assert (created.entity_type, created.entity_text, created.mention_count, created.variants) == ("orgName", "X", 2, ["Xie"])
    assert stats["person_to_organization"] == 1


def test_rename_is_reapplied_to_fresh_ner_row_and_keeps_old_forms_as_variants():
    row = entity("Jemenu Północnego", count=3, variants=["Jemenu Północnym"])
    entities = [row]

    _, touched, stats = run([decision("renamed", "Jemenu Północnego", new_text="Jemen Północny")], entities)

    assert stats == {"renamed": 1, "merged": 0, "deleted": 0}
    assert row.entity_text == "Jemen Północny"
    assert row.source == "manual"
    assert row.geocode_id is None
    assert {"Jemenu Północnego", "Jemenu Północnym", "Jemen Północny"} <= set(row.variants)
    assert list(touched.values()) == [row]


def test_rename_matches_a_surface_variant_of_the_fresh_row():
    row = entity("Jemen Pólnocny", variants=["Jemenu Północnego"])

    _, _, stats = run([decision("renamed", "Jemenu Północnego", new_text="Jemen Północny")], [row])

    assert stats["renamed"] == 1
    assert row.entity_text == "Jemen Północny"


def test_rename_into_an_existing_name_merges_instead_of_duplicating():
    old = entity("Jemenu Północnego", count=2)
    existing = entity("Jemen Północny", count=5)
    entities = [old, existing]

    session, touched, stats = run([decision("renamed", "Jemenu Północnego", new_text="Jemen Północny")], entities)

    assert stats["renamed"] == 1
    session.delete.assert_called_once_with(old)
    assert entities == [existing]
    assert existing.mention_count == 7
    assert existing.source == "manual"
    assert list(touched.values()) == [existing]


def test_rename_without_a_matching_mention_or_already_applied_is_a_noop():
    already = entity("Jemen Północny", variants=["Jemenu Północnego"], source="manual")
    session, touched, stats = run([
        decision("renamed", "Jemenu Północnego", new_text="Jemen Północny"),
        decision("renamed", "Nigdzie", new_text="Gdzieś"),
    ], [already])

    assert stats == {"renamed": 0, "merged": 0, "deleted": 0}
    assert touched == {}
    session.delete.assert_not_called()


def test_place_merge_folds_source_into_target_and_can_take_an_org_misclassification():
    kijow_org = entity("Kijów", entity_type="orgName", count=2)
    kijow = entity("Kijów", entity_type="geogName", count=4)
    entities = [kijow_org, kijow]

    session, touched, stats = run([
        decision("place_merged", "Kijów", entity_type="geogName",
                 source_entity_text="Kijów", source_entity_type="orgName", target_entity_text="Kijów"),
    ], entities)

    assert stats["merged"] == 1
    session.delete.assert_called_once_with(kijow_org)
    assert kijow.mention_count == 6
    assert kijow.source == "manual"


def test_place_merge_needs_both_sides_to_exist():
    aden = entity("Aden")
    session, _, stats = run([
        decision("place_merged", "Rijad", source_entity_text="Aden", target_entity_text="Rijad"),
    ], [aden])

    assert stats["merged"] == 0
    session.delete.assert_not_called()


def test_deleted_place_stays_deleted_but_only_by_exact_text():
    pilica = entity("Pilica")
    hidden = entity("Inna", variants=["Pilica"])
    entities = [pilica, hidden]

    session, _, stats = run([decision("deleted", "Pilica"), decision("rejected", "Pilica")], entities)

    assert stats["deleted"] == 1
    session.delete.assert_called_once_with(pilica)
    assert entities == [hidden]


def test_decisions_replay_in_order_so_a_later_rename_can_reuse_a_deleted_name():
    pilica = entity("Pilica")
    other = entity("Pilicą")
    entities = [pilica, other]

    _, _, stats = run([
        decision("deleted", "Pilica"),
        decision("renamed", "Pilicą", new_text="Pilica"),
    ], entities)

    assert stats["deleted"] == 1 and stats["renamed"] == 1
    assert [e.entity_text for e in entities] == ["Pilica"]


def test_replay_geocodes_touched_rows_without_geocode_and_swallows_failures():
    row = entity("Jemenu Północnego")
    session = MagicMock()
    session.scalars.side_effect = [
        MagicMock(all=lambda: [decision("renamed", "Jemenu Północnego", new_text="Jemen Północny")]),
        MagicMock(all=lambda: [row]),
    ]
    doc = MagicMock()

    with patch("library.place_verification.geocode_single_place", side_effect=RuntimeError("boom")) as geocode:
        stats = replay_manual_place_decisions(session, 1, doc)

    assert stats["renamed"] == 1
    geocode.assert_called_once_with(session, doc, row)


def test_replay_does_nothing_without_recorded_decisions():
    session = MagicMock()
    session.scalars.return_value = MagicMock(all=lambda: [])

    assert replay_manual_place_decisions(session, 1) == {}
    assert session.scalars.call_count == 1


def test_place_split_is_replayed_into_one_manual_row_per_part():
    row = entity("Pakistan Afganistan", count=2, variants=["Pakistanem Afganistanem"])
    rows = [row]
    session = MagicMock()
    touched, stats = apply_decisions(
        session, [decision("place_split", "Pakistan Afganistan", parts=["Pakistan", "Afganistan"])], rows,
    )
    assert row not in rows
    session.delete.assert_called_once_with(row)
    assert [(r.entity_text, r.mention_count, r.variants, r.source) for r in rows] == [
        ("Pakistan", 2, ["Pakistanem"], "manual"), ("Afganistan", 2, ["Afganistanem"], "manual"),
    ]
    assert list(touched.values()) == rows
    assert stats["split"] == 1


def test_place_split_folds_a_part_into_an_existing_place_and_ignores_a_missing_mention():
    compound = entity("Pakistan Afganistan", count=2)
    existing = entity("Pakistan", count=5)
    rows = [compound, existing]
    apply_decisions(MagicMock(), [decision("place_split", "Pakistan Afganistan", parts=["Pakistan", "Afganistan"])], rows)
    assert existing.mention_count == 7
    assert sorted(r.entity_text for r in rows) == ["Afganistan", "Pakistan"]
    gone = [entity("Iran")]
    _, _, stats = run([decision("place_split", "Pakistan Afganistan", parts=["Pakistan", "Afganistan"])], gone)
    assert "split" not in stats


def test_suggest_place_split_only_for_lists_of_countries():
    pytest.importorskip("unidecode")
    from library.entity_service import suggest_place_split
    assert suggest_place_split("Pakistanem Afganistanem") == ["Pakistan", "Afganistan"]
    assert suggest_place_split("Iran, Irak i Syria") == ["Iran", "Irak", "Syria"]
    assert suggest_place_split("Korea Południowa Japonia") == ["Korea Południowa", "Japonia"]
    assert suggest_place_split("Kijów Lwów") is None
    assert suggest_place_split("Polska") is None


def test_person_to_place_is_replayed_and_keeps_surface_forms():
    person = entity("Kandaharem", entity_type="persName", count=2, variants=["Kandahar"])
    rows = [person]
    session = MagicMock()
    touched, stats = apply_decisions(
        session, [decision("person_to_place", "Kandaharem", entity_type="persName", new_text="Kandahar")], rows,
    )
    assert person not in rows
    session.delete.assert_called_once_with(person)
    place = rows[0]
    assert (place.entity_type, place.entity_text, place.mention_count, place.source) == ("placeName", "Kandahar", 2, "manual")
    assert place.variants == ["Kandaharem"]
    assert list(touched.values()) == [place]
    assert stats["person_to_place"] == 1


def test_replay_onto_a_surviving_manual_row_does_not_count_the_mention_again():
    """Doc #10872: "Kalinigrad" went 3 -> 4 -> 5 -> 6 because every refresh re-folded a fresh persName."""
    survivor = entity("Kalinigrad", count=3, source="manual")
    fresh = entity("Kalinigrad", entity_type="persName", count=1)
    rows = [survivor, fresh]
    _, _, stats = run([decision("person_to_place", "Kalinigrad", entity_type="persName", new_text="Kalinigrad")], rows)
    assert survivor.mention_count == 3
    assert rows == [survivor]
    assert stats["person_to_place"] == 1


def test_first_conversion_into_an_existing_ner_place_still_adds_the_count():
    place = entity("Kandahar", count=3)
    person = entity("Kandaharem", entity_type="persName", count=2)
    run([decision("person_to_place", "Kandaharem", entity_type="persName", new_text="Kandahar")], [place, person])
    assert place.mention_count == 5
    assert place.source == "manual"


def test_replayed_merge_and_rename_collision_do_not_inflate_a_surviving_target():
    target = entity("Kaliningrad", count=4, source="manual")
    fresh_source = entity("Królewiec", count=1)
    run([decision("place_merged", "Kaliningrad", source_entity_text="Królewiec", source_variants=["Królewiec"],
                  target_entity_text="Kaliningrad")], [target, fresh_source])
    assert target.mention_count == 4

    target2 = entity("Kijów", count=5, source="manual")
    other = entity("Kijowa", count=2)
    run([decision("renamed", "Kijowa", new_text="Kijów")], [target2, other])
    assert target2.mention_count == 5


def test_two_fresh_sources_merged_into_a_new_target_are_both_counted():
    target = entity("Kaliningrad", count=2)
    first = entity("Królewiec", count=1)
    second = entity("Königsberg", count=3)
    run([
        decision("place_merged", "Kaliningrad", source_entity_text="Królewiec", source_variants=[],
                 target_entity_text="Kaliningrad"),
        decision("place_merged", "Kaliningrad", source_entity_text="Königsberg", source_variants=[],
                 target_entity_text="Kaliningrad"),
    ], [target, first, second])
    assert target.mention_count == 6


def test_replayed_split_and_organization_conversions_respect_surviving_rows():
    survivor_place = entity("Pakistan", count=2, source="manual")
    compound = entity("Pakistanem Afganistanem", count=1)
    run([decision("place_split", "Pakistanem Afganistanem", parts=["Pakistan", "Afganistan"])],
        [survivor_place, compound])
    assert survivor_place.mention_count == 2

    survivor_person = entity("Rawit Ruja", entity_type="persName", count=2, source="manual")
    org = entity("Rawit Ruja", entity_type="orgName", count=1)
    session = MagicMock()
    session.scalars.return_value.all.return_value = []
    apply_decisions(session, [decision("organization_to_person", "Rawit Ruja", entity_type="orgName")],
                    [survivor_person, org])
    assert survivor_person.mention_count == 2


def test_organization_to_place_is_replayed_and_drops_the_organization_link():
    org = entity("Tela Avivwu", entity_type="orgName", count=1)
    rows = [org]
    session = MagicMock()
    link = SimpleNamespace(id=3)
    session.scalars.return_value.all.return_value = [link]
    touched, stats = apply_decisions(
        session, [decision("organization_to_place", "Tela Avivwu", entity_type="orgName", new_text="Tel Awiw")], rows,
    )
    session.delete.assert_any_call(link)
    session.delete.assert_any_call(org)
    place = rows[0]
    assert (place.entity_type, place.entity_text, place.source, place.variants) == (
        "placeName", "Tel Awiw", "manual", ["Tela Avivwu"])
    assert list(touched.values()) == [place]
    assert stats["organization_to_place"] == 1


def test_organization_to_person_is_replayed_without_touching_places():
    org = entity("Rawit Ruja", entity_type="orgName", count=2, variants=["Rawit Ruja"])
    rows = [org]
    session = MagicMock()
    session.scalars.return_value.all.return_value = []
    touched, stats = apply_decisions(
        session, [decision("organization_to_person", "Rawit Ruja", entity_type="orgName")], rows,
    )
    person = rows[0]
    assert (person.entity_type, person.entity_text, person.mention_count, person.source) == (
        "persName", "Rawit Ruja", 2, "manual")
    assert touched == {}
    assert stats["organization_to_person"] == 1


def test_organization_conversion_without_a_matching_row_is_a_no_op():
    rows = [entity("NATO", entity_type="orgName")]
    _, _, stats = run([decision("organization_to_place", "Tela Avivwu", entity_type="orgName")], rows)
    assert rows[0].entity_type == "orgName"
    assert "organization_to_place" not in stats
