import sys
import types

from library.recipe_book_parser import Recipe
from library.recipe_book_photos import (
    Photo,
    candidates_for,
    match_photo,
    match_with_vision,
    recipes_by_page,
    thumb_key,
)


def _recipe(title: str, *pages: int) -> Recipe:
    return Recipe(title=title, pages=list(pages))


def _photo(page: int, full_page: bool = True) -> Photo:
    return Photo(page=page, rect=(0, 0, 468, 581), full_page=full_page)


def test_thumb_key_is_derived_from_the_storage_key():
    assert thumb_key("documents/10880/images/0.jpg") == "documents/10880/images/0_thumb.jpg"


def test_candidates_cover_neighbouring_pages_for_full_page_photos():
    index = recipes_by_page(
        [_recipe("Guacamole", 62), _recipe("Pasta", 65), _recipe("Hummus", 66, 67), _recipe("Zupa", 90)]
    )
    assert [r.title for r in candidates_for(_photo(64), index)] == ["Guacamole", "Pasta", "Hummus"]
    assert [r.title for r in candidates_for(_photo(64, full_page=False), index)] == []


def test_no_candidates_means_no_match_and_no_model_call():
    calls = []
    match = match_photo(_photo(10), b"jpeg", {}, vision=lambda *a: calls.append(a))
    assert match.recipe_key is None and match.method == "none" and calls == []


def test_vision_choice_above_threshold_is_accepted_below_is_rejected():
    index = recipes_by_page([_recipe("Guacamole", 62), _recipe("Pasta szpinakowa", 65)])
    accepted = match_photo(_photo(63), b"jpeg", index, vision=lambda jpeg, titles: (1, 0.95, "pasta"))
    assert accepted.recipe_key == "pasta szpinakowa" and accepted.method == "vision"
    rejected = match_photo(
        _photo(63), b"jpeg", index, vision=lambda jpeg, titles: (1, 0.8, "pasta"), min_confidence=0.85
    )
    assert rejected.recipe_key is None and rejected.confidence == 0.8
    none = match_photo(_photo(63), b"jpeg", index, vision=lambda jpeg, titles: (None, 1.0, "brak potrawy"))
    assert none.recipe_key is None and none.dish == "brak potrawy"


def _fake_ai(monkeypatch, answers):
    calls = []

    def ai_ask(prompt, model, **kwargs):
        calls.append(kwargs)
        return types.SimpleNamespace(response_text=answers[min(len(calls), len(answers)) - 1])

    monkeypatch.setitem(sys.modules, "library.ai", types.SimpleNamespace(ai_ask=ai_ask))
    return calls


def test_vision_answer_in_a_json_fence_is_parsed(monkeypatch):
    _fake_ai(monkeypatch, ['```json\n{"dish": "Guacamole", "index": 0, "confidence": 1.0}\n```'])
    assert match_with_vision(b"jpeg", ["Guacamole", "Pasta"]) == (0, 1.0, "Guacamole")


def test_vision_retries_after_an_empty_answer_and_ignores_out_of_range_index(monkeypatch):
    calls = _fake_ai(monkeypatch, [None, '{"dish": "x", "index": 7, "confidence": 0.9}'])
    assert match_with_vision(b"jpeg", ["A", "B"]) == (None, 0.9, "x")
    assert len(calls) == 2


def test_vision_garbage_gives_no_match(monkeypatch):
    _fake_ai(monkeypatch, ["nie wiem", "nie wiem", "nie wiem"])
    assert match_with_vision(b"jpeg", ["A"]) == (None, 0.0, "")
