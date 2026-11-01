"""The geopolitics analysis prompt lives in ``prompt_templates`` (task ``geopolitics_events``)."""

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

pytest.importorskip("sqlalchemy")
pytest.importorskip("flask")
pytest.importorskip("jinja2")

from flask import Flask, g

from library import geopolitics_detect as detect
from library import prompt_template_routes as routes
from library import prompt_templates as pt
from library.db.models import PromptTemplate

TASK = pt.TASK_GEOPOLITICS
VARIANT = "event_extraction"

# What `build_prompt` produced before the text moved into the template (captured from the old f-string).
GOLDEN = {
    0: 'Jesteś analitykiem geopolityki. Z poniższego fragmentu wydobądź KONKRETNE, datowane wydarzenia\nmiędzynarodowe (decyzje rządów, wybory, sankcje, umowy, ataki, ucieczki polityków, przejęcia platform itp.).\n\nZASADY:\n- Zwracaj tylko wydarzenia, które fragment opisuje wprost. Nie zgaduj. Jeśli nic nie pasuje, zwróć [].\n- "country" to wyłącznie slug z listy: laos, chiny, stany-zjednoczone.\n- "role": actor (sprawca), target (cel), affected (dotknięty), location (miejsce).\n- "date": YYYY-MM-DD, YYYY-MM lub YYYY. Data odniesienia (kiedy tekst powstał / został pobrany): 2026-10-27.\n  Wyrażenia względne ("w ubiegłym miesiącu", "od stycznia", "obecnie") przelicz na datę względem daty odniesienia.\n  Jeśli nie da się ustalić nawet roku, wpisz null. W "date_text" podaj oryginalne sformułowanie daty z tekstu (lub null).\n- "quote": DOKŁADNY, dosłowny cytat ze fragmentu (do 300 znaków), który potwierdza wydarzenie.\n- "relation" ustaw TYLKO wtedy, gdy samo wydarzenie wyraźnie zmienia lub ujawnia stosunek jednego z krajów\n  do drugiego; w przeciwnym razie null. Pojedyncze zdarzenie (np. ucieczka polityka do obcego kraju)\n  zwykle NIE wystarcza do oceny stosunków. Osie: political (Polityczna); security (Bezpieczeństwo).\n  "from" i "to" muszą być uczestnikami tego wydarzenia; "score" od -2 (wroga) do 2 (sojusznicza); "confidence" 0-1.\n- Maksymalnie 6 wydarzeń.\n\nOdpowiedz WYŁĄCZNIE tablicą JSON:\n[{"title": "...", "description": "...", "date": "...", "date_text": "...", "quote": "...",\n  "participants": [{"country": "slug", "role": "actor"}],\n  "relation": null lub {"from": "slug", "to": "slug", "axis": "political", "score": -1, "confidence": 0.5, "rationale": "..."}}]\n\nFRAGMENT:\n"""\nFragment tekstu o Laosie.\n"""',
    1: 'Jesteś analitykiem geopolityki. Z poniższego fragmentu wydobądź KONKRETNE, datowane wydarzenia\nmiędzynarodowe (decyzje rządów, wybory, sankcje, umowy, ataki, ucieczki polityków, przejęcia platform itp.).\n\nZASADY:\n- Zwracaj tylko wydarzenia, które fragment opisuje wprost. Nie zgaduj. Jeśli nic nie pasuje, zwróć [].\n- "country" to wyłącznie slug z listy: (brak kandydatów).\n- "role": actor (sprawca), target (cel), affected (dotknięty), location (miejsce).\n- "date": YYYY-MM-DD, YYYY-MM lub YYYY. Data odniesienia (kiedy tekst powstał / został pobrany): nieznana.\n  Wyrażenia względne ("w ubiegłym miesiącu", "od stycznia", "obecnie") przelicz na datę względem daty odniesienia.\n  Jeśli nie da się ustalić nawet roku, wpisz null. W "date_text" podaj oryginalne sformułowanie daty z tekstu (lub null).\n- "quote": DOKŁADNY, dosłowny cytat ze fragmentu (do 300 znaków), który potwierdza wydarzenie.\n- "relation" ustaw TYLKO wtedy, gdy samo wydarzenie wyraźnie zmienia lub ujawnia stosunek jednego z krajów\n  do drugiego; w przeciwnym razie null. Pojedyncze zdarzenie (np. ucieczka polityka do obcego kraju)\n  zwykle NIE wystarcza do oceny stosunków. Osie: political (Polityczna); security (Bezpieczeństwo).\n  "from" i "to" muszą być uczestnikami tego wydarzenia; "score" od -2 (wroga) do 2 (sojusznicza); "confidence" 0-1.\n- Maksymalnie 6 wydarzeń.\n\nOdpowiedz WYŁĄCZNIE tablicą JSON:\n[{"title": "...", "description": "...", "date": "...", "date_text": "...", "quote": "...",\n  "participants": [{"country": "slug", "role": "actor"}],\n  "relation": null lub {"from": "slug", "to": "slug", "axis": "political", "score": -1, "confidence": 0.5, "rationale": "..."}}]\n\nFRAGMENT:\n"""\nDrugi fragment.\n"""',
}

CASES = [
    ("Fragment tekstu o Laosie.", ["laos", "chiny", "stany-zjednoczone"], "2026-10-27"),
    ("Drugi fragment.", [], None),
]


@pytest.mark.parametrize("index", [0, 1])
def test_builtin_template_reproduces_the_previous_prompt(index):
    fragment, slugs, published = CASES[index]
    assert detect.build_prompt(fragment, slugs, published) == GOLDEN[index]


def test_task_is_registered_with_variables_and_a_valid_builtin():
    assert pt.VARIANTS[TASK] == (VARIANT,)
    assert set(pt.VARIABLES[TASK]) == {"fragment", "countries", "reference_date", "axes", "max_events"}
    builtin = pt.builtin(TASK, VARIANT)
    assert builtin.label == "event_extraction-builtin" and builtin.system is None
    pt.validate(TASK, VARIANT, builtin.system, builtin.user)


@pytest.mark.parametrize(
    "user_template", ["{{ nieznana }}", "{{ zle", "{% for x in fragment %}{{ x }}{% endfor %}{{ y }}"]
)
def test_invalid_geopolitics_templates_are_rejected(user_template):
    with pytest.raises(pt.TemplateInvalid):
        pt.validate(TASK, VARIANT, None, user_template)


def test_template_may_use_only_its_own_variables():
    with pytest.raises(pt.TemplateInvalid):
        pt.validate(TASK, VARIANT, None, "{{ catalog }}")  # a content-group variable
    pt.validate(TASK, VARIANT, "System: {{ axes }}", "Kraje: {{ countries }}\n{{ fragment }}")


def test_content_group_variants_do_not_accept_geopolitics_variables():
    with pytest.raises(pt.TemplateInvalid):
        pt.validate(pt.TASK_CONTENT_GROUPS, "feed_item", None, "{{ fragment }} {{ catalog }} {{ material }}")


def test_new_version_is_numbered_per_task_and_variant():
    session = MagicMock()
    session.scalar.return_value = 4
    session.scalars.return_value.all.return_value = []
    row = pt.create_version(session, TASK, VARIANT, None, "{{ fragment }} {{ countries }}", note="krótszy")
    assert (row.task, row.variant, row.version, row.is_active) == (TASK, VARIANT, 5, True)
    assert pt.label_for(row.variant, row.version) == "event_extraction-v5"


@pytest.fixture
def client(monkeypatch):
    app = Flask(__name__)
    app.register_blueprint(routes.bp)

    @app.before_request
    def auth():
        g.auth = SimpleNamespace(kind="user", user_id=1)

    monkeypatch.setattr(routes, "get_scoped_session", MagicMock())
    return app.test_client()


def test_listing_for_the_task_returns_its_variant_variables_and_builtin(client):
    body = client.get(f"/prompt_templates?task={TASK}").get_json()
    assert body["task"] == TASK and body["variants"] == [VARIANT]
    assert "fragment" in body["variables"] and "catalog" not in body["variables"]
    assert "{{ fragment }}" in body["builtin"][VARIANT]["user_template"]
    assert client.get("/prompt_templates?task=nope").status_code == 400


def test_create_validates_against_the_geopolitics_task(client, monkeypatch):
    assert (
        client.post("/prompt_templates", json={"task": TASK, "variant": "feed_item", "user_template": "x"}).status_code
        == 400
    )
    assert (
        client.post(
            "/prompt_templates", json={"task": TASK, "variant": VARIANT, "user_template": "{{ catalog }}"}
        ).status_code
        == 400
    )
    saved = PromptTemplate(id=9, task=TASK, variant=VARIANT, version=2, user_template="u", is_active=True)
    create = MagicMock(return_value=saved)
    monkeypatch.setattr(pt, "create_version", create)
    response = client.post(
        "/prompt_templates", json={"task": TASK, "variant": VARIANT, "user_template": "{{ fragment }}"}
    )
    assert response.status_code == 201 and response.get_json()["template"]["label"] == "event_extraction-v2"


def test_preview_renders_a_sample_without_calling_a_model(client):
    response = client.post(
        "/prompt_templates/preview",
        json={
            "task": TASK,
            "variant": VARIANT,
            "user_template": "K={{ countries }} D={{ reference_date }} M={{ max_events }}",
        },
    )
    assert response.status_code == 200
    assert response.get_json()["user"] == "K=polska, niemcy D=2026-01-01 M=6"
    assert response.get_json()["document_id"] is None
    bad = client.post(
        "/prompt_templates/preview", json={"task": TASK, "variant": VARIANT, "user_template": "{{ catalog }}"}
    )
    assert bad.status_code == 400
