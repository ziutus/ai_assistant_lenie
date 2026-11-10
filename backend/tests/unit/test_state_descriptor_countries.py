"""A bare "Królestwo" stands for the kingdom named in the same chapter (doc 11238: Arabia Saudyjska)."""

import json
from types import SimpleNamespace

import pytest

pytest.importorskip("unidecode")

from library import entity_service, state_descriptor_countries as sdc
from library.country_gazetteer import canonical_country_name

HOUTHI_CHAPTER = (
    "## Houthi podali cenę pokoju\n\n"
    "Wojska saudyjskie miały iść na Sanę. Królestwo zwróciło się do grupy z prośbą o wyjaśnienie, "
    "co mają zrobić. Huti chcieliby, aby królestwo oficjalnie uznało bojowników za władców Jemenu. "
    "Arabia Saudyjska nadal może wplątać się w nowy konflikt, a granica Królestwa jest długa."
)
OTHER_CHAPTER = "## Ropa w dół\n\nCeny ropy spadły, a Iran i Stany Zjednoczone negocjują."
TEXT = OTHER_CHAPTER + "\n\n" + HOUTHI_CHAPTER


def verdict(**overrides):
    return {"id": 0, "class": "country", "confidence": "high", "rationale": "odwołanie do państwa"} | overrides


@pytest.fixture(autouse=True)
def no_config(monkeypatch):
    monkeypatch.setattr(sdc, "_model", lambda: "test-model")


@pytest.fixture
def llm(monkeypatch):
    calls = []

    def fake_ask(prompt, **kwargs):
        calls.append((prompt, kwargs))
        return SimpleNamespace(response_text=json.dumps({"results": [verdict()]}))

    monkeypatch.setattr("library.ai.ai_ask", fake_ask)
    monkeypatch.setattr(sdc, "_model", lambda: "test-model")
    return calls


def test_every_country_is_a_gazetteer_country():
    for form, countries in sdc.COUNTRIES_BY_FORM.items():
        assert form in sdc.DESCRIPTOR_FORMS
        for country in countries:
            assert canonical_country_name(country) == country, country


def test_descriptor_next_to_a_fitting_country_is_a_candidate():
    [candidate] = sdc.find_descriptor_candidates(TEXT)
    assert candidate["country"] == "Arabia Saudyjska"
    assert candidate["form"] == "kingdom"
    assert candidate["count"] == 3
    assert candidate["variants"] == ["Królestwo", "królestwo", "Królestwa"]
    assert "zwróciło się do grupy" in candidate["context"]


@pytest.mark.parametrize(
    "sentence",
    [
        "Arabia Saudyjska i Królestwo Danii podpisały umowę.",
        "Arabia Saudyjska, Zjednoczone Królestwo i Francja.",
        "Arabia Saudyjska a Królestwo Niebieskie.",
        "Arabia Saudyjska i królestwo zwierząt.",
    ],
)
def test_proper_names_and_other_nouns_are_not_candidates(sentence):
    assert sdc.find_descriptor_candidates(sentence) == []


def test_a_republic_is_never_the_referent():
    assert sdc.find_descriptor_candidates("Huti walczą w Jemenie, a królestwo traci. Iran patrzy.") == []


def test_the_country_must_be_named_in_the_same_chapter():
    text = "## Jeden\n\nArabia Saudyjska to duży kraj.\n\n## Dwa\n\nPrzyszło królestwo i nikt nie wie które."
    assert sdc.find_descriptor_candidates(text) == []


def test_several_fitting_countries_are_all_candidates():
    names = {c["country"] for c in sdc.find_descriptor_candidates("Maroko i Jordania. Królestwo zaprotestowało.")}
    assert names == {"Maroko", "Jordania"}


def test_no_candidate_means_no_llm_call(llm):
    assert sdc.classify_state_descriptors("Arabia Saudyjska bez żadnego opisu ustroju.") == []
    assert llm == []


def test_confirmed_descriptor_is_counted_for_the_country(llm):
    confirmed = sdc.confirmed_state_descriptors(TEXT, "Wojna", 7)
    assert confirmed == {"Arabia Saudyjska": {"count": 3, "variants": ["Królestwo", "królestwo", "Królestwa"]}}
    assert llm[0][1]["document_id"] == 7
    assert "Arabia Saudyjska" in llm[0][0]


@pytest.mark.parametrize(
    "answer",
    [
        verdict(**{"class": "other"}),
        verdict(**{"class": "uncertain"}),
        verdict(confidence="low"),
    ],
)
def test_other_verdicts_confirm_nothing(monkeypatch, answer):
    monkeypatch.setattr(
        "library.ai.ai_ask", lambda *a, **k: SimpleNamespace(response_text=json.dumps({"results": [answer]}))
    )
    assert sdc.confirmed_state_descriptors(TEXT) == {}


@pytest.mark.parametrize("failure", ["not json", RuntimeError("down")])
def test_llm_failure_fails_open(monkeypatch, failure):
    def fake_ask(*args, **kwargs):
        if isinstance(failure, Exception):
            raise failure
        return SimpleNamespace(response_text=failure)

    monkeypatch.setattr("library.ai.ai_ask", fake_ask)
    assert sdc.confirmed_state_descriptors(TEXT) == {}


def test_two_confirmed_countries_for_one_descriptor_are_ambiguous(monkeypatch):
    answers = {"results": [verdict(id=0), verdict(id=1)]}
    monkeypatch.setattr("library.ai.ai_ask", lambda *a, **k: SimpleNamespace(response_text=json.dumps(answers)))
    assert sdc.confirmed_state_descriptors("Maroko i Jordania. Królestwo zaprotestowało.") == {}


def test_only_the_confirmed_one_of_two_countries_wins(monkeypatch):
    # candidates follow the order of COUNTRIES_BY_FORM: id 0 = Jordania, id 1 = Maroko
    answers = {"results": [verdict(id=0, **{"class": "other"}), verdict(id=1)]}
    monkeypatch.setattr("library.ai.ai_ask", lambda *a, **k: SimpleNamespace(response_text=json.dumps(answers)))
    confirmed = sdc.confirmed_state_descriptors("Maroko i Jordania. Królestwo zaprotestowało.")
    assert list(confirmed) == ["Maroko"]


def test_entity_groups_get_the_descriptor_as_a_variant_of_the_country(llm):
    groups = {
        ("placeName", "Arabia Saudyjska"): {"count": 2, "variants": ["Arabii Saudyjskiej"], "raw_lemmas": []},
        ("persName", "Kowalski"): {"count": 1, "variants": []},
    }
    entity_service._apply_state_descriptors(groups, TEXT, "Wojna", 7)
    group = groups[("placeName", "Arabia Saudyjska")]
    assert group["count"] == 5
    assert group["variants"] == ["Arabii Saudyjskiej", "Królestwo", "królestwo", "Królestwa"]
    assert ("persName", "Kowalski") in groups


def test_a_new_country_group_is_created_when_ner_never_found_the_country(llm):
    groups = {}
    entity_service._apply_state_descriptors(groups, TEXT, "", 7)
    assert groups == {
        ("placeName", "Arabia Saudyjska"): {
            "count": 3,
            "variants": ["Królestwo", "królestwo", "Królestwa"],
            "raw_lemmas": ["Arabia Saudyjska"],
        }
    }


def test_mentions_are_taken_from_a_ner_group_of_the_same_spelling(llm):
    groups = {("orgName", "Królestwo"): {"count": 5, "variants": ["Królestwo"]}}
    entity_service._apply_state_descriptors(groups, TEXT, "", 7)
    assert groups[("orgName", "Królestwo")]["count"] == 2
    groups = {("orgName", "Królestwo"): {"count": 3, "variants": ["Królestwo"]}}
    entity_service._apply_state_descriptors(groups, TEXT, "", 7)
    assert ("orgName", "Królestwo") not in groups


def test_unconfirmed_descriptor_keeps_ner_groups(monkeypatch):
    monkeypatch.setattr(
        "library.ai.ai_ask",
        lambda *a, **k: SimpleNamespace(response_text=json.dumps({"results": [verdict(**{"class": "other"})]})),
    )
    groups = {("orgName", "Królestwo"): {"count": 5, "variants": ["Królestwo"]}}
    entity_service._apply_state_descriptors(groups, TEXT, "", 7)
    assert groups == {("orgName", "Królestwo"): {"count": 5, "variants": ["Królestwo"]}}
