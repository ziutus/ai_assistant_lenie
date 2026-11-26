import json
from decimal import Decimal
from types import SimpleNamespace

import pytest

from library.relation_extraction import Names, chunk_text, extract_relations, parse_answer, quote_matches


TEXT = "Ada Brzask pracuje dla Lunorii."


def proposal(**changes):
    return dict(subject="Ada Brzask", subject_type="osoba", relation="pracownik", object="Lunoria",
                object_type="organizacja", claim="fakt", quote=TEXT, **changes)


def run(rows, verdicts=None, **kwargs):
    answers = iter([json.dumps({"relations": rows}), json.dumps({"verdicts": verdicts or []})])
    return extract_relations(TEXT, [], "mock", ask=lambda *a, **k: next(answers), **kwargs)


def test_chunks_prefer_paragraphs_and_keep_long_sentences():
    assert chunk_text("**Pierwszy.**\n\nDrugi.", 12) == ["Pierwszy.", "Drugi."]
    assert chunk_text("Pierwsze zdanie. Drugie zdanie.", 18) == ["Pierwsze zdanie.", "Drugie zdanie."]
    assert chunk_text("Zdanie bez miejsca na podział", 5) == ["Zdanie bez miejsca na podział"]
    assert chunk_text(" \n ") == []
    with pytest.raises(ValueError):
        chunk_text(TEXT, 0)


@pytest.mark.parametrize("text,bad,count", [
    ('Proza ```json\n{"relations":[{"subject":"Ada"}]}\n```', False, 1),
    ('{"relations":[{"subject":"Ada"},{"subject":"urwane', True, 1),
    ('{"relations":[]}', False, 0),
    ('{"relations":[{"subject":"urwane', True, 0),
    ('nie JSON', True, 0),
])
def test_parse_salvage(text, bad, count):
    rows, unreadable = parse_answer(text)
    assert len(rows) == count
    assert unreadable is bad


def test_quote_tolerance_is_narrow():
    assert quote_matches('„Ada **Brzask**” pracuje', 'Ada Brzask\n pracuje')
    assert not quote_matches('Ada nie pracuje', TEXT)
    assert not quote_matches('ada Brzask', TEXT)
    assert not quote_matches('Ada … pracuje', TEXT)
    assert not quote_matches('""', TEXT)


def test_names_exact_ambiguous_and_legal_form():
    names = Names([
        {"type": "persName", "name": "Ada Brzask", "variants": ["Ady Brzask", "Brzask"]},
        {"type": "persName", "name": "Iwo Brzask", "variants": ["Brzask"]},
        {"type": "orgName", "name": "Lunoria sp. z o.o.", "variants": []},
    ])
    assert names.resolve("Ady Brzask", "osoba") == "Ada Brzask"
    assert names.resolve("Iwo Brzask", "osoba") == "Iwo Brzask"
    assert names.resolve("Brzask", "osoba") == "Brzask"
    assert names.resolve("Lunoria", "organizacja") == "Lunoria sp. z o.o."
    assert names.in_chunk(TEXT)[0]["name"] == "Ada Brzask"
    ambiguous = Names([{"type": "orgName", "name": n} for n in ("Lunoria sp. z o.o.", "Lunoria S.A.")])
    assert ambiguous.resolve("Lunoria", "organizacja") == "Lunoria"


@pytest.mark.parametrize("verdict", ["przeczy", "nie_wynika"])
def test_rejected_verification(verdict):
    result = run([proposal()], [{"id": 0, "verdict": verdict}])
    assert result["relations"] == []
    assert result["report"]["rejected"] == {verdict: 1}


def test_verification_correction_and_swap():
    result = run([proposal()], [{"id": 0, "verdict": "potwierdza", "relation": "doradca",
                                "claim": "deklaracja_strony", "direction_ok": False}])
    row = result["relations"][0]
    assert (row["subject"], row["subject_type"], row["object"]) == ("Lunoria", "organizacja", "Ada Brzask")
    assert row["relation"] == "doradca" and row["claim"] == "deklaracja_strony"
    assert row["unverified"] is False


@pytest.mark.parametrize("verdicts", [[], [{"id": 0}], [{"id": 0, "verdict": "potwierdza", "relation": []}],
                                     [{"id": 0, "verdict": "potwierdza", "relation": "invented"}],
                                     [{"id": 0}, {"id": 0, "verdict": "przeczy"}]])
def test_missing_or_invalid_verdict_keeps_unverified(verdicts):
    assert run([proposal()], verdicts)["relations"][0]["unverified"]


def test_validation_unknown_role_self_and_quote():
    rows = [dict(proposal(), relation="nieznana"), dict(proposal(), quote="Inny tekst"),
            dict(proposal(), object="Ada Brzask"), dict(proposal(), claim="nieznany"), None]
    result = run(rows, verify=False)
    assert result["relations"][0]["original_relation"] == "nieznana"
    assert result["relations"][0]["relation"] == "inna"
    assert result["report"]["rejected"] == {"quote_not_found": 1, "self_relation": 1,
                                             "invalid_claim": 1, "invalid_fields": 1}


def test_symmetric_dedupe_keeps_all_quotes_and_claim_evidence():
    a = dict(proposal(), relation="partner", quote="Ada Brzask")
    b = dict(proposal(), relation="partner", subject="Lunoria", object="Ada Brzask", quote="pracuje dla Lunorii.",
             subject_type="organizacja", object_type="osoba", claim="deklaracja_strony")
    rows = run([a, b], verify=False)["relations"]
    assert len(rows) == 1
    assert rows[0]["quotes"] == [a["quote"], b["quote"]]
    assert len(rows[0]["evidence"]) == 2


def test_failed_call_continues_and_usage_unknown():
    calls = []

    def ask(*args, **kwargs):
        calls.append(kwargs)
        if len(calls) == 1:
            raise RuntimeError("model unavailable")
        return '{"relations":[]}'

    result = extract_relations("Pierwszy.\n\nDrugi.", [], "mock", ask=ask, chunk_chars=10)
    assert result["report"]["calls"] == 2
    assert result["report"]["failed_calls"] == 1
    assert result["report"]["llm_cost_amount"] is None


def test_usage_capability_degradation_and_context():
    calls = []
    usage = SimpleNamespace(usage_log_id=1, total_tokens=24,
                            cost=SimpleNamespace(total_cost=Decimal("0.001"), currency="EUR", status="estimated"))

    def ask(query, model, **kwargs):
        calls.append((query, kwargs))
        return SimpleNamespace(response_text='{"relations":[]}', usage=usage)

    result = extract_relations(TEXT, [], "mock", ask=ask, document_id=12, system_supported=False)
    assert "system_prompt" not in calls[0][1] and "response_format" not in calls[0][1]
    assert "Kierunek" in calls[0][0]
    assert calls[0][1]["operation"] == "relation_extraction" and calls[0][1]["document_id"] == 12
    assert result["report"]["llm_cost_amount"] == "0.001"
    assert result["report"]["llm_tokens"] == 24


def test_truncated_extraction_and_failed_verifier_are_reported():
    answers = iter(['{"relations":[' + json.dumps(proposal()) + ', {"subject":', 'bad JSON'])
    result = extract_relations(TEXT, [], "mock", ask=lambda *a, **k: next(answers))
    assert result["report"]["unreadable_answers"] == 2
    assert result["relations"][0]["unverified"]


def test_grouped_entities_and_batched_verification_schema():
    calls = []

    def ask(query, model, **kwargs):
        calls.append((json.loads(query), kwargs))
        if len(calls) == 1:
            return json.dumps({"relations": [proposal(), dict(proposal(), relation="doradca")]})
        raise RuntimeError("verifier failed")

    entities = {"persName": [{"text": "Ada Brzask", "canonical_name": "Ada Brzask"}],
                "orgName": [{"text": "Lunoria", "variants": ["Lunorii"]}],
                "placeName": [{"text": "Mgliste"}]}
    result = extract_relations(TEXT, entities, "mock", ask=ask, structured_output=True)
    assert len(calls) == 2
    assert [p["id"] for p in calls[1][0]["proposals"]] == [0, 1]
    assert calls[0][0]["known_entities"][0]["name"] == "Ada Brzask"
    assert len(calls[0][0]["known_entities"]) == 2
    assert calls[0][1]["response_format"]["type"] == "json_schema"
    assert calls[1][1]["response_format"]["json_schema"]["name"] == "verdicts"
    assert all(r["unverified"] and r["subject"] == "Ada Brzask" for r in result["relations"])
    assert result["report"]["failed_calls"] == 1


def test_quote_must_be_in_its_chunk_and_empty_response_does_not_abort():
    answers = iter([json.dumps({"relations": [proposal()]}), None])
    result = extract_relations("Inny akapit.\n\n" + TEXT, [], "mock", chunk_chars=len(TEXT),
                               ask=lambda *a, **k: next(answers))
    assert result["relations"] == []
    assert result["report"]["calls"] == 2
    assert result["report"]["unreadable_answers"] == 1
    assert result["report"]["rejected"] == {"quote_not_found": 1}


def test_registry_name_absent_from_the_document_is_not_used():
    from library.relation_extraction import Names

    names = Names([
        {"entity_type": "persName", "text": "Adam Z.", "variants": ["Adam Z."], "canonical_name": "Adam Zmyślony"},
        {"entity_type": "persName", "text": "Brzaska", "variants": ["Brzaska"], "canonical_name": "Brzask"},
    ])
    assert names.resolve("Adam Z.", "osoba") == "Adam Z."
    assert names.resolve("Brzaska", "osoba") == "Brzask"


def test_indirect_ownership_of_a_person_is_set_aside():
    from library.relation_extraction import split_indirect_ownership

    def row(subject, obj, kind="osoba"):
        return {"subject": subject, "object": obj, "relation": "udzialowiec", "subject_type": kind}

    rows = [row("Ada Brzask", "Lunoria"), row("Lunoria", "Mokradło", "organizacja"), row("Ada Brzask", "Mokradło")]
    direct, indirect = split_indirect_ownership(rows)
    assert indirect == [rows[2]] and direct == rows[:2]
