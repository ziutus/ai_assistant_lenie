"""Independent model results, user edits, and races around shared photos."""

from types import SimpleNamespace
from io import BytesIO
from unittest.mock import MagicMock

import pytest
from PIL import Image

from library import contact_photos as photos
from library.db.models import Contact


@pytest.fixture
def setup(monkeypatch):
    photo = SimpleNamespace(storage_key="contacts/one/photo.png", user_description="To bliźnięta.",
                            user_description_revision=3, ai_descriptions={})
    contact = SimpleNamespace(id=1, photo_storage_key=photo.storage_key)
    session = MagicMock()
    session.get.side_effect = lambda model, key, **kw: contact if model is Contact else photo
    monkeypatch.setattr(photos, "load_config", lambda: {"CLOUDFERRO_SHERLOCK_KEY": "test"})
    storage = MagicMock()
    image = BytesIO()
    Image.new("RGB", (32, 24), "white").save(image, format="PNG")
    storage.get_bytes.return_value = image.getvalue()
    monkeypatch.setattr(photos, "storage_from_config", lambda cfg: storage)
    ask = MagicMock(return_value=SimpleNamespace(response_text="Cztery osoby na zdjęciu.", usage=None))
    monkeypatch.setattr(photos, "ai_ask", ask)
    return contact, photo, session, ask


def payload(photo, **extra):
    return {"storage_key": photo.storage_key, "model": photos.SHERLOCK_VISION_MODELS[0], **extra}


def test_user_edit_preserves_ai_and_checks_revision(setup):
    _, photo, session, ask = setup
    photo.ai_descriptions = {"model": {"text": "Widoczne osoby"}}
    result, status = photos.update_description(session, 1, payload(
        photo, user_description="Mąż i bliźnięta", user_description_revision=3))
    assert status == 200
    assert result["photo"]["user_description_revision"] == 4
    assert photo.ai_descriptions["model"]["text"] == "Widoczne osoby"
    ask.assert_not_called()
    _, status = photos.update_description(session, 1, payload(
        photo, user_description="stary zapis", user_description_revision=3))
    assert status == 409
    assert photo.user_description == "Mąż i bliźnięta"


def test_two_models_and_regeneration_preserve_user_knowledge(setup):
    _, photo, session, ask = setup
    for model in photos.SHERLOCK_VISION_MODELS:
        _, status = photos.generate_description(session, 1, payload(photo, model=model))
        assert status == 200
    assert set(photo.ai_descriptions) == set(photos.SHERLOCK_VISION_MODELS)
    assert photo.user_description == "To bliźnięta."
    assert photo.user_description_revision == 3
    for call in ask.call_args_list:
        assert "To bliźnięta" not in str(call)
        assert call.kwargs["image_media_type"] == "image/jpeg"
        assert call.kwargs["operation"] == "contact_photo_description"


def test_failed_second_model_keeps_successful_first(setup):
    _, photo, session, ask = setup
    photos.generate_description(session, 1, payload(photo))
    ask.side_effect = RuntimeError("private provider response")
    result, status = photos.generate_description(session, 1, payload(photo, model=photos.SHERLOCK_VISION_MODELS[1]))
    assert status == 502
    assert "private" not in str(result)
    assert len(photo.ai_descriptions) == 1
    assert photo.user_description == "To bliźnięta."


def test_replaced_photo_rejects_stale_ai_result(setup):
    contact, photo, session, ask = setup
    def replace(*args, **kwargs):
        contact.photo_storage_key = "new-photo.png"
        return SimpleNamespace(response_text="stary obraz", usage=None)
    ask.side_effect = replace
    _, status = photos.generate_description(session, 1, payload(photo))
    assert status == 409
    assert photo.ai_descriptions == {}
    session.commit.assert_not_called()


def test_concurrent_other_model_is_not_overwritten(setup):
    _, photo, session, ask = setup
    other = photos.SHERLOCK_VISION_MODELS[1]
    def concurrent(*args, **kwargs):
        photo.ai_descriptions = {other: {"text": "Wynik równoległy"}}
        photo.user_description = "Nowa wiedza zapisana podczas generowania"
        return SimpleNamespace(response_text="Cztery osoby", usage=None)
    ask.side_effect = concurrent
    _, status = photos.generate_description(session, 1, payload(photo))
    assert status == 200
    assert photo.ai_descriptions[other]["text"] == "Wynik równoległy"
    assert photo.user_description == "Nowa wiedza zapisana podczas generowania"


def test_concurrent_same_model_is_not_overwritten(setup):
    _, photo, session, ask = setup
    model = photos.SHERLOCK_VISION_MODELS[0]
    def concurrent(*args, **kwargs):
        photo.ai_descriptions = {model: {"text": "Nowszy wynik"}}
        return SimpleNamespace(response_text="starszy wynik", usage=None)
    ask.side_effect = concurrent
    _, status = photos.generate_description(session, 1, payload(photo))
    assert status == 409
    assert photo.ai_descriptions[model]["text"] == "Nowszy wynik"


def by_photo_id(session, photo):
    photo.id = "8f1f3c9a-0000-4000-8000-000000000001"
    photo.subject_kind = "unknown"
    photo.people_count = None
    photo.classification_revision = 0
    session.execute.return_value.scalar_one_or_none.return_value = photo
    return photo.id


def test_describe_by_photo_id_needs_no_contact(setup):
    _, photo, session, ask = setup
    photo_id = by_photo_id(session, photo)
    result, status = photos.generate_description(
        session, None, {"model": photos.SHERLOCK_VISION_MODELS[0]}, photo_id=photo_id)
    assert status == 200
    assert result["photo"]["ai_descriptions"][photos.SHERLOCK_VISION_MODELS[0]]["text"] == "Cztery osoby na zdjęciu."
    assert "To bliźnięta" not in str(ask.call_args)


def test_classification_suggestion_is_on_demand_and_not_persisted(setup):
    _, photo, session, ask = setup
    photo_id = by_photo_id(session, photo)
    ask.return_value = SimpleNamespace(response_text='{"subject_kind": "people", "people_count": 4}', usage=None)
    result, status = photos.suggest_classification(session, photo_id, {})
    assert (status, result) == (200, {"subject_kind": "people", "people_count": 4})
    assert photo.subject_kind == "unknown" and photo.classification_revision == 0
    session.commit.assert_not_called()
    call = ask.call_args
    assert call.kwargs["operation"] == "contact_photo_classification"
    assert "To bliźnięta" not in str(call)


@pytest.mark.parametrize("answer", ["nie json", '{"subject_kind": "unknown", "people_count": null}',
                                    '{"subject_kind": "no_people", "people_count": 2}'])
def test_invalid_classification_suggestion_is_rejected(setup, answer):
    _, photo, session, ask = setup
    photo_id = by_photo_id(session, photo)
    ask.return_value = SimpleNamespace(response_text=answer, usage=None)
    assert photos.suggest_classification(session, photo_id, {})[1] == 502
    session.commit.assert_not_called()


def test_classification_update_checks_revision_and_no_people_count(setup):
    _, photo, session, ask = setup
    photo_id = by_photo_id(session, photo)
    assert photos.update_classification(session, photo_id, {
        "subject_kind": "no_people", "people_count": 2, "classification_revision": 0})[1] == 400
    assert photos.update_classification(session, photo_id, {
        "subject_kind": "people", "people_count": 3, "classification_revision": 5})[1] == 409
    result, status = photos.update_classification(session, photo_id, {
        "subject_kind": "people", "people_count": 3, "classification_revision": 0})
    assert status == 200
    assert (photo.subject_kind, photo.people_count, photo.classification_revision) == ("people", 3, 1)
    ask.assert_not_called()


@pytest.mark.parametrize("body", [None, [], {"user_description": 1},
    {"user_description": "x", "user_description_revision": True},
    {"user_description": "x" * 12001, "user_description_revision": 3}])
def test_invalid_user_description_is_rejected(setup, body):
    _, _, session, ask = setup
    assert photos.update_description(session, 1, body)[1] == 400
    session.commit.assert_not_called()
    ask.assert_not_called()


def test_non_image_and_large_image_never_reach_model(setup, monkeypatch):
    _, photo, session, ask = setup
    storage = MagicMock()
    monkeypatch.setattr(photos, "storage_from_config", lambda cfg: storage)
    for content, status in [(b"not an image", 415), (b"x" * (photos.MAX_IMAGE_BYTES + 1), 413)]:
        storage.get_bytes.return_value = content
        assert photos.generate_description(session, 1, payload(photo))[1] == status
    ask.assert_not_called()


def test_clear_description_preserves_model_results(setup):
    _, photo, session, _ = setup
    assert photos.update_description(session, 1, payload(photo, user_description="", user_description_revision=3))[1] == 200
    assert photo.user_description is None


def test_vision_image_fits_gateway_and_preserves_original():
    import random
    original = BytesIO()
    Image.frombytes("RGB", (1800, 1200), random.Random(42).randbytes(1800 * 1200 * 3)).save(
        original, format="PNG")
    data = original.getvalue()
    encoded = photos.prepare_vision_image(data)
    assert len(encoded) <= photos.MAX_VISION_IMAGE_BYTES
    assert original.getvalue() == data
    with Image.open(BytesIO(encoded)) as image:
        assert image.format == "JPEG"
        assert max(image.size) <= 1600
        assert image.width / image.height == pytest.approx(1.5, abs=0.01)


def test_vision_image_corrects_orientation_and_flattens_transparency():
    original = BytesIO()
    source = Image.new("RGBA", (40, 20), (0, 0, 0, 0))
    exif = Image.Exif()
    exif[274] = 6
    source.save(original, format="PNG", exif=exif)
    with Image.open(BytesIO(photos.prepare_vision_image(original.getvalue()))) as image:
        assert image.size == (20, 40)
        assert image.getpixel((10, 10)) == (255, 255, 255)


def test_photo_level_shared_description_logs_all_contacts(setup, monkeypatch):
    contact, photo, session, ask = setup
    session.execute.return_value.scalar_one_or_none.return_value = photo
    other = SimpleNamespace(id=2)
    session.execute.return_value.scalars.return_value.all.return_value = [contact, other]
    log = MagicMock()
    monkeypatch.setattr(photos, "record_contact_change", log)
    result, status = photos.update_description(session, None, {
        "user_description": "Shared", "user_description_revision": 3,
    }, photo_id="00000000-0000-4000-8000-000000000001")
    assert status == 200
    assert result["photo"]["user_description"] == "Shared"
    assert [call.args[1].id for call in log.call_args_list] == [1, 2]
    ask.assert_not_called()


@pytest.mark.parametrize("kind,count", [("no_people", 0), ("people", -1), ("people", True),
                                        ("invalid", None), ("people", 1.5)])
def test_invalid_classification(setup, kind, count):
    _, _, session, ask = setup
    assert photos.update_classification(session, "id", {
        "subject_kind": kind, "people_count": count, "classification_revision": 0,
    })[1] == 400
    ask.assert_not_called()


def test_classification_revision_and_no_automatic_ai(setup):
    _, photo, session, ask = setup
    photo.classification_revision = 0
    session.execute.return_value.scalar_one_or_none.return_value = photo
    body = {"subject_kind": "no_people", "people_count": None, "classification_revision": 0}
    assert photos.update_classification(session, "id", body)[1] == 200
    assert photos.update_classification(session, "id", body)[1] == 409
    assert photo.subject_kind == "no_people"
    assert photo.people_count is None
    ask.assert_not_called()


def test_suggestion_is_explicit_unpersisted_and_prompt_has_no_user_data(setup):
    _, photo, session, ask = setup
    photo.subject_kind = "unknown"
    photo.people_count = None
    photo.classification_revision = 7
    session.execute.return_value.scalar_one_or_none.return_value = photo
    ask.return_value.response_text = '{"subject_kind":"people","people_count":3}'
    result, status = photos.suggest_classification(session, "id", {})
    assert status == 200
    assert result == {"subject_kind": "people", "people_count": 3}
    assert photo.subject_kind == "unknown"
    assert photo.classification_revision == 7
    session.commit.assert_not_called()
    ask.assert_called_once()
    assert ask.call_args.kwargs["operation"] == "contact_photo_classification"
    assert ask.call_args.kwargs["model"] == "google/gemma-4-31B-it"
    assert photo.user_description not in str(ask.call_args)


def test_invalid_suggestion_never_persists(setup):
    _, photo, session, ask = setup
    session.execute.return_value.scalar_one_or_none.return_value = photo
    ask.return_value.response_text = '{"subject_kind":"no_people","people_count":2}'
    assert photos.suggest_classification(session, "id", {})[1] == 502
    session.commit.assert_not_called()


@pytest.mark.parametrize("value", [True, False, None])
def test_link_tristate_and_revision(setup, value):
    contact, photo, session, ask = setup
    session.execute.return_value.scalar_one_or_none.return_value = photo
    link = SimpleNamespace(depicts_contact=None, revision=0)
    session.get.side_effect = lambda model, key, **kw: contact if model is Contact else link
    body = {"depicts_contact": value, "revision": 0}
    assert photos.update_link(session, "id", 1, body)[1] == 200
    assert link.depicts_contact is value
    assert photos.update_link(session, "id", 1, body)[1] == 409
    ask.assert_not_called()


def test_photo_routes_and_legacy_adapters(setup, monkeypatch):
    from flask import Flask
    from library.contact_routes import bp
    from library import contact_routes

    _, photo, session, ask = setup
    photo.id = "00000000-0000-4000-8000-000000000001"
    photo.classification_revision = 0
    session.execute.return_value.scalar_one_or_none.return_value = photo
    session.execute.return_value.all.return_value = []
    monkeypatch.setattr(contact_routes, "get_scoped_session", lambda: session)
    storage = MagicMock()
    storage.presigned_get_url.return_value = "/photo.png"
    monkeypatch.setattr(photos, "storage_from_config", lambda cfg: storage)
    app = Flask(__name__)
    app.register_blueprint(bp)
    client = app.test_client()
    response = client.get(f"/contact_photos/{photo.id}")
    assert response.status_code == 200
    assert response.json["id"] == photo.id
    assert response.json["photo_url"] == "/photo.png"
    assert response.json["contacts"] == []
    assert client.patch(f"/contact_photos/{photo.id}/description", json={
        "user_description": "Shared", "user_description_revision": 3,
    }).status_code == 200
    assert client.patch("/contacts/1/photo/description", json={
        "storage_key": photo.storage_key, "user_description": "Adapter", "user_description_revision": 4,
    }).status_code == 200
    assert client.patch("/contacts/1/photo/description", json={
        "storage_key": "another-photo", "user_description": "Wrong", "user_description_revision": 5,
    }).status_code == 409
    assert client.patch(f"/contact_photos/{photo.id}/classification", json={
        "subject_kind": "people", "people_count": 2, "classification_revision": 0,
    }).status_code == 200
    ask.assert_not_called()


def test_photo_migration_upgrade_and_downgrade_sql():
    from io import StringIO
    from pathlib import Path
    from alembic.migration import MigrationContext
    from alembic.operations import Operations
    from alembic.script import ScriptDirectory

    scripts = ScriptDirectory(str(Path(__file__).resolve().parents[2] / "alembic"))
    assert scripts.get_heads() == ["b7e41c9a620d"]
    revision = scripts.get_revision("b7e41c9a620d")
    assert revision.down_revision == "a5c27d9e4b18"
    output = StringIO()
    context = MigrationContext.configure(dialect_name="postgresql", opts={"as_sql": True, "output_buffer": output})
    with Operations.context(context):
        revision.module.upgrade()
        revision.module.downgrade()
    sql = output.getvalue()
    assert "id UUID NOT NULL DEFAULT gen_random_uuid() UNIQUE" in sql
    assert "PRIMARY KEY (contact_id, storage_key)" in sql
    assert "SELECT id, photo_storage_key FROM contacts WHERE photo_storage_key IS NOT NULL" in sql
    assert "DROP TABLE contact_photo_links" in sql
    assert "DROP COLUMN id" in sql


def test_photo_detail_lists_all_linked_contacts(setup):
    _, photo, session, _ = setup
    session.execute.return_value.scalar_one_or_none.return_value = photo
    contacts = [Contact(id=1, uuid="one", first_name="Anna", photo_storage_key=photo.storage_key),
                Contact(id=2, uuid="two", display_label="Child", photo_storage_key="new-photo")]
    session.execute.return_value.all.return_value = [
        (contact, SimpleNamespace(depicts_contact=value, revision=revision))
        for contact, value, revision in zip(contacts, [False, None], [2, 0])
    ]
    photos.storage_from_config({}).presigned_get_url.return_value = "/photo.png"
    result, status = photos.get_photo(session, "id")
    assert status == 200
    assert result["contacts"] == [
        {"contact_id": 1, "uuid": "one", "display_name": "Anna", "depicts_contact": False,
         "link_revision": 2, "is_current_photo": True},
        {"contact_id": 2, "uuid": "two", "display_name": "Child", "depicts_contact": None,
         "link_revision": 0, "is_current_photo": False},
    ]
