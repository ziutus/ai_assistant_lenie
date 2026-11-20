# OpenRouter

**Status: działa, główny dostawca modeli zewnętrznych** (obok CloudFerro). Od
2026-11-19 lista dozwolonych modeli zawiera tylko OpenRouter i CloudFerro; bezpośredni
OpenAI i Google Vertex są w `llm_models` oznaczone jako `retired` (wracają jednym
`PATCH /llm_models/<id>`, [ADR-032](../adr/adr-032-llm-models-db-backed.md)).

OpenRouter to pośrednik z jednym kluczem i jednym API zgodnym z OpenAI dla wielu
modeli (Mistral, Claude, Gemma, Llama, GPT i inne). Dzięki temu nowy model to wiersz
w tabeli `llm_models`, a nie nowy adapter.

## Co ta integracja robi

| Element | Gdzie | Uwagi |
|---|---|---|
| Completion (`openrouter/<dostawca>/<model>`) | `library/api/openrouter/openrouter_completion.py`, routing w `library/ai.py` | prefiks `openrouter/` jest nasz; do API idzie id bez niego. Obsługuje `system_prompt` i `response_format` (JSON schema) |
| Katalog modeli i ceny | `library/api/openrouter/openrouter_catalog.py` | publiczne `GET /api/v1/models`, **bez klucza i bez tekstu dokumentów**, więc działa także przy wyłączonej integracji; cache 6 h w procesie |
| Saldo klucza | `library/api/openrouter/openrouter_key.py` | `GET /api/v1/key`, cache 60 s; `GET /openrouter_balance` i `GET /provider_balances` (`/service-status`) |
| Koszty | `library/llm_usage/recorder.py` | rzeczywisty koszt z `usage.cost` odpowiedzi (`cost_status='reported'`), a gdy go brak, szacunek z katalogu |
| Modele decyzyjne | `library/entity_sense_classifier.py` | `https://openrouter.ai/api/alpha/decisions` (typowane pytania wyboru), drugi w kolejności po Fabryce AI |

## Konfiguracja

- `OPENROUTER_API_KEY` w Vault (jak każdy klucz, zob. [README](README.md)).
- `OPENROUTER_ENABLED` (`1`/`true`/`yes`/`on`): **domyślnie integracja jest wyłączona**.
  Treść dokumentu opuszcza wtedy Lenie i trafia do OpenRoutera oraz do dostawcy
  modelu, więc modele `openrouter/*` znikają z pickerów, dopóki flaga nie zostanie
  włączona. Odczyt katalogu cen jest dozwolony zawsze.
- Limit wydatków ustawia się na kluczu w panelu OpenRoutera. Lenie czyta go przez
  `/key` tym samym kluczem. Saldo całego konta (`/credits`) wymaga klucza
  zarządzającego i celowo go nie używamy.

## Obserwacja statusu i koszty

- Każde wywołanie trafia do `llm_usage_logs` (`provider='openrouter'`), widoczne na
  `/llm-costs`. Nie korzysta z `external_service_events`.
- Saldo i ostrzeżenie „mało” (20 % limitu lub mniej) jest w sekcji „Salda i limity
  płatnych usług” na `/service-status`. Bez limitu na kluczu znane jest tylko zużycie.
- Pełne zapytania i odpowiedzi modeli decyzyjnych są audytowane w `llm_call_payloads`
  (z wyjątkiem danych prywatnych, `store_payload=False`).

## Dobór modeli

- Domyślny model kuracji feedów: `openrouter/mistralai/mistral-small-3.2-24b-instruct`.
- Modele „frontier” do analizy rozdziałów (Claude Sonnet/Fable przez OpenRouter):
  pomiar jakości i kosztów w [event-detection-model-comparison.md](../event-detection-model-comparison.md).
- Strukturalne wyjście (`response_format`) jest wysyłane tylko do modeli, które
  katalog OpenRoutera oznacza jako `structured_outputs`.
- Jak zbudować funkcję opartą na LLM (picker z cenami, prompty, walidacja):
  [llm-features-howto.md](../llm-features-howto.md).

## Zasady

Klucz wyłącznie w Vault. Prywatnych treści (zdjęcia i adresy kontaktów, wiadomości
WhatsApp) nie wysyłamy do żadnego zewnętrznego modelu bez potrzeby; funkcje na takich
danych mają `store_payload=False`. Ogólne zasady dla integracji: [README.md](README.md).
