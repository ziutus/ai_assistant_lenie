"""Independent model results, user edits, and races around shared photos."""

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

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
    storage.get_bytes.return_value = b"\x89PNG\r\n\x1a\n" + b"x" * 30
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
        assert call.kwargs["image_media_type"] == "image/png"
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
