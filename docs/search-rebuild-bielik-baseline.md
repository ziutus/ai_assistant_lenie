# Etap 10 — baseline ewaluacji Bielika 11B

Data pomiaru: 2026-07-18. Model: `Bielik-11B-v3.0-Instruct` przez CloudFerro Sherlock. Fixture: `backend/tests/fixtures/search_query_cases.json`, wersja 1.

## Metodyka

Runner `backend/imports/evaluate_search_queries.py` wywołuje produkcyjny `parse_search_query()` sekwencyjnie i porównuje tylko pola jawnie obecne w częściowym `expected`. Wartości domenowe są serializowane do postaci kontraktu JSON, a dodatkowe poprawne pola nie obniżają wyniku.

Korpus zawiera 43 przypadki, ale pusty `edge-06` jest celowo pomijany przed LLM zgodnie z kontraktem walidacji requestu. Baseline obejmuje 42 wywołania. Po raporcie runner usuwa tylko rekordy audytu i usage o identyfikatorach zwróconych przez przebieg. Kontrola po teście potwierdziła po 0 pozostawionych rekordów.

## Wyniki

| Metryka | Wynik |
|---|---:|
| Poprawny JSON | 42/42 (100%) |
| Przypadki ze wszystkimi oczekiwanymi polami | 22/42 (52,38%) |
| Status `parsed` / `ambiguous` | 39 / 3 |
| Fallback parsera | 0 |
| Łączna / średnia latencja | 131 183 ms / 3 123,40 ms |
| Łączne / średnie tokeny | 104 899 / 2 497,60 |
| Łączny / średni koszt | 0,0587434400 / 0,0013986533 EUR (`estimated`) |

### Trafność per pole

| Pole | Poprawne / ocenione | Trafność |
|---|---:|---:|
| `author_name` | 2/2 | 100% |
| `publisher_name` | 3/3 | 100% |
| `publisher_domain` | 1/1 | 100% |
| `languages` | 2/2 | 100% |
| `sort` | 3/3 | 100% |
| `published_on_to` | 4/4 | 100% |
| `published_on_from` | 4/5 | 80% |
| `subject_period_end_year` | 8/10 | 80% |
| `subject_period_start_year` | 7/9 | 77,78% |
| `temporal_expression` | 4/6 | 66,67% |
| `query` | 25/41 | 60,98% |
| `document_types` | 3/5 | 60% |
| `discovery_source_name` | 0/2 | 0% |
| `ingested_at_from`, `ingested_at_to` | po 0/1 | 0% |
| `clarification_required` | 0/1 | 0% |

## Najczęstsze klasy błędów

1. `query` — 16 rozbieżności. Model często pozostawia słowa sterujące lub wydzielony filtr (`artykuły`, `teksty`, `książki`, okres), zamiast samego tematu. Prompt injection został skrócony do `DROP TABLE`, a bezsensowny tekst zwrócił `query=null`.
2. Okres treści — po 2 błędy start/end: nierozpoznany okres faraonów oraz dodatnie `500` bez okna `around` dla „500 p.n.e.”.
3. Discovery source — 2/2 niewykryte; treść pozostała w `query`.
4. Typ dokumentu — 2 rozbieżności: zbyt wąski lub zbyt szeroki zestaw typów wideo.
5. Daty — „po 2020” dało `2020-01-01` zamiast `2021-01-01`; brak zakresu `ingested_at` dla stycznia 2026.
6. Dopytanie — „pokaż wszystko” nie ustawiło preferowanego `clarification_required=true`. Fixture dokumentuje, że lista wszystkiego też jest dopuszczalna, więc ścisły wynik zaniża tu jakość użytkową.

Różnice stylistyczne w `temporal_expression` są liczone jako błędy ścisłe. Fixture opisuje też dopuszczalne alternatywy w `notes`, których scorer celowo nie interpretuje. Wynik jest konserwatywnym baseline’em, nie oceną semantyczną człowieka.

## Decyzja po pierwszej iteracji

Nie zmieniono promptu w baseline’owym przebiegu. Najpierw utrwalamy pomiar i klasy błędów; kolejna iteracja powinna dodać ogólne reguły oraz przykłady dla oczyszczania `query`, discovery source, dat dodania i BCE, po czym uruchomić identyczny korpus ponownie. Nie ma podstaw do fine-tuningu na 42 odpowiedziach.

Powtórzenie z katalogu `backend/` przy skonfigurowanym Sherlocku i NAS:

```powershell
$env:PYTHONPATH='.'
.venv\Scripts\python.exe imports\evaluate_search_queries.py --output C:\tmp\search-stage10-baseline.json
```
