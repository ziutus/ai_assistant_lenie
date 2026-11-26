# Porównanie modeli ekstrakcji relacji

Pipeline `backend/library/relation_extraction.py` tworzy propozycje relacji osób i organizacji
na podstawie tekstu. Nie zapisuje relacji ani encji do bazy. Wywołanie modelu jest wstrzykiwane;
CLI używa `ai_ask`, które prowadzi zwykły rejestr użycia LLM (`operation=relation_extraction`,
`document_id`). Wersja promptu: `relations-pl-v1`. To narzędzie do porównania modeli, bez UI,
migracji, automatycznego zatwierdzania ani zapisywania relacji.

## Uruchomienie

Z katalogu `backend`, z `PYTHONPATH=.` i skonfigurowanym środowiskiem dostawcy modelu:

```powershell
$env:PYTHONPATH='.'
python imports/relation_extraction_eval.py --input C:/private/relation-input --models model-a,model-b --gold C:/private/relation-gold --out C:/private/relation-results --runs 2
```

Tryb API zamiast `--input`: `--documents 1,2`. Wymaga `LENIE_API_URL` i `LENIE_API_KEY`.
Czyta wyłącznie GET `/website_get?id=...` i GET `/website_entities?id=...` z nagłówkiem
`x-api-key`; nie odświeża NER. Tekst pochodzi z `text`, z fallbackiem do `text_raw`.
`--chunk-chars` (domyślnie 3500) określa docelowy rozmiar fragmentu; `--no-verify` wyłącza
drugie przejście. `--runs` domyślnie wynosi 1. Uruchomienie CLI faktycznie wywołuje modele;
testy jednostkowe używają wyłącznie atrap.

Katalog wejściowy zawiera pliki JSON, np. poniższy całkowicie fikcyjny przykład:

```json
{
  "id": 1,
  "text": "Ada Brzask pracuje dla Lunorii.",
  "entities": [
    {"entity_type": "persName", "canonical_name": "Ada Brzask", "variants": ["Ady Brzask"]},
    {"entity_type": "orgName", "canonical_name": "Lunoria", "variants": ["Lunorii"]}
  ]
}
```

Obsługiwany jest też format encji API: obiekt z listami `persName` i `orgName`,
z polami `text`, `canonical_name` i `variants`. Identyfikatory dokumentów muszą być dodatnimi liczbami.

Wyniki zawierają cytaty: `--out` musi wskazywać katalog poza repozytorium Git. Sprawdzenie
obejmuje rozwiązane dowiązania/junctions, katalog worktree i nadrzędny checkout.
Każdy dokument/model/przebieg otrzymuje osobny JSON; nazwa modelu jest zastępowana skrótem SHA-256
w nazwie pliku. Osobny Markdown dla każdego modelu zawiera wiersz na dokument i przebieg.
Ponowne uruchomienie z tym samym katalogiem nadpisuje odpowiadające pliki; do archiwizacji używaj nowego katalogu.

## Ekstrakcja i weryfikacja

Tekst jest oczyszczany z wyróżnień Markdown. Podział preferuje akapity, potem zdania;
pojedyncze długie zdanie może przekroczyć limit, aby nie utracić kontekstu. Prompt zawiera
zamkniętą listę ról z kierunkiem, typy twierdzeń, zakaz pozytywnego odczytania negacji
i rozróżnienie własności pośredniej od bezpośredniej. Model dostaje tylko znane encje obecne
w danym fragmencie. Cytat jest sprawdzany jako ciągły fragment tekstu z tolerancją białych znaków,
cudzysłowów i wyróżnień Markdown; parafrazy nie przechodzą.

Jedno wywołanie weryfikatora na fragment ocenia wszystkie poprawne strukturalnie propozycje.
`przeczy` i `nie_wynika` usuwają propozycję; `potwierdza` może poprawić rolę, typ twierdzenia
i kierunek. Niepełny, błędny lub brakujący werdykt pozostawia `unverified=true`.
Wyłączenie weryfikatora również pozostawia tę flagę. Nieznana rola trafia do `inna`,
z zachowaniem `original_relation`; niepoprawne typy encji/twierdzeń są odrzucane.

Nazwy są dopasowywane dokładnie po normalizacji wielkości liter i odstępów. Organizacje
mogą być dopasowane bez formy prawnej tylko przy jednoznacznym wyniku, przez istniejące
`company_registry_service.normalize_name`. Samo wspólne nazwisko nie scala osób.
Dedup obejmuje `(subject, relation, object)`; `rodzina`, `umowa`, `partner`, `wspolpracownik`
są symetryczne. `quotes` zachowuje wszystkie różne cytaty, a `evidence` także ich typy twierdzeń,
daty i statusy weryfikacji. Główny `claim` pochodzi z pierwszej propozycji i jest używany w scoringu;
rozbieżne twierdzenia należy obejrzeć w `evidence`. Zbiorcze `unverified` jest prawdziwe, jeśli
choć jeden element dowodowy nie został zweryfikowany.

CLI sprawdza możliwości dostawcy. Gdy brak roli systemowej, instrukcje są jawnie umieszczane
w zapytaniu użytkownika (`system_prompt_mode=user_instructions`). JSON Schema jest wysyłany
tylko przy pozytywnym wyniku istniejącego `supports_structured_output`; inaczej model dostaje
instrukcję tekstową JSON i podlega tej samej walidacji. Lookup modeli/katalogu odbywa się tylko
w rzeczywistym CLI, nie w czystym pipeline z atrapą.

## Gold i metryki

Plik `<gold>/<document_id>.json`, wyłącznie fikcyjne dane w przykładzie:

```json
{
  "relations": [
    {"subject": "Ada Brzask", "relations": ["pracownik", "doradca"], "object": "Lunoria", "claim": "fakt", "required": true},
    {"subject": "Iwo Brzask", "relation": "partner", "object": "Lunoria", "claim": "deklaracja_strony", "required": false}
  ],
  "forbidden": [
    {"subject": "Ada Brzask", "relation": "udzialowiec", "object": "Lunoria", "reason": "Tekst zaprzecza własności"}
  ],
  "aliases": {"Ada Brzask": ["Ady Brzask"]}
}
```

- Dopasowanie: nazwy po aliasach i normalizacji, akceptowana rola, zgodny kierunek (dowolny dla ról symetrycznych).
  Niejednoznaczny alias nie jest scalany. Każdy wymagany wpis gold może zostać zaliczony raz.
- `found`: wszystkie propozycje; `correct`: trafienia w wymagany gold. `required` domyślnie jest prawdziwe.
- Dopasowania `required:false` są neutralne: pomijane w mianowniku precision i w brakach recall.
- Precision = correct / (found − neutralne). Recall = trafione wymagane / wszystkie wymagane.
  F1 jest średnią harmoniczną; metryka z pustym mianownikiem jest nieznana (`null`).
- `wrong_direction_count`: rola i nazwy pasują, ale kierunek niesymetrycznej relacji jest odwrócony.
- `forbidden_hits`: trafienia w zakazane relacje, oceniane przed gold i liczone jako błędy precision.
  To osobna kategoria najpoważniejszych błędów, nigdy poprawne dopasowanie.
- `unmatched`: propozycje bez dopasowania, wraz z pełną listą do ręcznego przeglądu w JSON.
  Precision traktuje je jako błędne, choć gold może być niepełny. Powtórne trafienie już zaliczonego gold jest unmatched.
- `claim_type_accuracy`: zgodność claim wśród poprawnie dopasowanych wymaganych relacji; nie zmienia precision/recall.
- Raport obejmuje odrzucenia według powodu, liczbę prób wywołań, błędy wywołań i nieczytelne odpowiedzi,
  tokeny, koszt z `response.usage`, walutę, status kosztu i czas. Nie wylicza cen samodzielnie.
  Niepełne koszty/tokeny pozostają nieznane. Ucięty JSON może dostarczyć kompletne obiekty poprzedzające ucięcie;
  nadal liczy się jako nieczytelna odpowiedź. Awaria nie zatrzymuje kolejnych fragmentów.

Bez gold (lub bez pliku dla dokumentu) dostępne są liczba propozycji i statystyki pipeline,
a metryki jakości pozostają nieznane. JSON zawiera również listę pominiętych wymaganych relacji.

## Wyniki

### Pierwszy przebieg, 2026-11-26 (wzorzec roboczy, przed poprawką nazw)

Jeden artykuł z 27 wymaganymi zależnościami, na którym wszystkie modele odpowiedziały (u jednego modelu 1 z 10
wywołań się nie powiodło). Jeden przebieg na model.

| Model | Znalezione z wymaganych | Precyzja (nieprzejrzany wzorzec) | Zależności zaprzeczone w tekście |
|---|---|---|---|
| Claude Sonnet 5.5 | 25/27 | 0,60 | 0 |
| Claude Fable 5.2 | 22/27 | 0,55 | 1 |
| Mistral Small 3.2 | 22/27 | 0,43 | 3 |
| Bielik 11B v3.0 | 19/27 | 0,46 | 2 |
| Gemma 3 27B | 17/27 | 0,37 | 0 |
| Llama 3.1 8B | 8/27 | 0,50 | 0 |

Pozostałe artykuły nie są jeszcze porównywalne: limit płatnego dostawcy wyczerpał się w trakcie, a wyniki zaniża
dopasowywanie nazw w odmianie i zbyt wąski kierunek ról płatniczych we wzorcu.
\n

### Przeliczenie na wzorcu v2 i podpowiedź v2, 2026-11-26

Wzorzec v2: płatności i umowy liczone w obu kierunkach, dopisane pominięte zależności jako opcjonalne; nazwy w
odmianie dopasowywane automatycznie. Cztery artykuły, 57 wymaganych zależności. Zapisane odpowiedzi modeli
przeliczono bez nowych wywołań (`--rescore`).

| Model (podpowiedź v1) | Znalezione | Precyzja | Zaprzeczone | Uwagi |
|---|---|---|---|---|
| Claude Sonnet 5.5 | 40/57 | 0,54 | 0 | komplet wywołań |
| Bielik 11B v3.0 | 34/57 | 0,23 | 2 | komplet wywołań |
| Claude Fable 5.2 | 33/57 | 0,47 | 1 | 12 wywołań nieudanych |
| Gemma 3 27B | 32/57 | 0,25 | 0 | 7 wywołań nieudanych |
| Mistral Small 3.2 | 22/57 | 0,43 | 3 | 17 wywołań nieudanych |
| Llama 3.1 8B | 9/57 | 0,36 | 0 | komplet wywołań |

Bielik z podpowiedzią v2 (trzy przebiegi): średnio 35/57, precyzja 0,23, 1,7 zaprzeczonej zależności na przebieg.
Na artykule, na którego błędach powstała podpowiedź, wynik wzrósł z 19/27 do 22-24/27 i zniknęły zaprzeczone
zależności; na pozostałych nie ma poprawy, więc to dopasowanie do jednego tekstu. Bielik nadal nie rozpoznaje
informacji od anonimowych źródeł i potrafi wymyślić pokrewieństwo na podstawie wspólnego nazwiska.

