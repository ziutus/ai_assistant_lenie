# Workflow analizy `document_removed_lines`

## Cel

Tabela `document_removed_lines` zawiera tekst usunięty ręcznie podczas review dokumentów oraz całe chunki odrzucone jako `SZUM` lub `REKLAMA`. Jest kolejką kandydatów do ulepszania automatycznego cleanera, a nie listą gotowych reguł.

Workflow jest przeznaczony do prowadzonej w rozmowie analizy przez Claude Code lub Codex. Agent przygotowuje dowody, proponuje zmianę i po jej wdrożeniu zapisuje decyzję w bazie. Tylko rekordy ze statusem `pending` podlegają analizie.

## Statusy

| Status | Znaczenie |
|---|---|
| `pending` | Rekord nie został jeszcze rozstrzygnięty. |
| `rule_added` | Na podstawie rekordu dodano lub rozszerzono regułę i test. |
| `already_covered` | Istniejąca reguła już obejmuje ten przypadek; nie jest potrzebna zmiana. |
| `rejected` | Tekst nie nadaje się na regułę, np. jest treścią artykułu lub przypadkiem zbyt specyficznym. |

Statusy końcowe zapobiegają analizowaniu tych samych rekordów w kolejnych rozmowach. Nie zmieniaj rozstrzygniętego statusu bez wyraźnego powodu i opisu w `review_note`.

## Zasady bezpieczeństwa reguł

1. Nie zakładaj, że ręcznie usunięty tekst jest szumem na każdej stronie portalu.
2. Preferuj regułę ograniczoną do domeny lub sekcji serwisu. Reguła globalna wymaga dowodów z wielu niezależnych portali.
3. Proste, stabilne stringi i regexy umieszczaj w `backend/data/site_rules.json`.
4. Logikę kontekstową, zależną od sąsiednich linii albo struktury treści, umieszczaj w `backend/library/article_cleaner.py`.
5. Reguła nie może usuwać poprawnej treści artykułu. Dodaj przypadek pozytywny i regresyjny pokazujący tekst, który ma pozostać.
6. Grupuj powtarzające się wzorce. Nie twórz osobnej reguły dla każdej różnicy w interpunkcji, dacie lub tytule zajawki.
7. Nie oznaczaj rekordów jako rozstrzygnięte przed wdrożeniem i przejściem testów.

## Etap 1: pobranie kandydatów

Z katalogu `backend` uruchom:

```powershell
$env:PYTHONPATH='.'
.\.venv\Scripts\python.exe scripts\review_removed_lines.py --list --limit 100
```

Na Linux/WSL:

```bash
cd backend
PYTHONPATH=. .venv/bin/python scripts/review_removed_lines.py --list --limit 100
```

Jeśli do ustalenia domeny, dokumentu albo częstotliwości potrzebne jest szersze zapytanie, użyj zapytania tylko do odczytu:

```sql
SELECT
    drl.id,
    drl.document_id,
    drl.run_id,
    drl.source,
    wd.url,
    drl.line_text,
    drl.created_at
FROM document_removed_lines AS drl
JOIN web_documents AS wd ON wd.id = drl.document_id
WHERE drl.review_status = 'pending'
ORDER BY drl.created_at, drl.id;
```

Nie pobieraj ponownie `rule_added`, `already_covered` ani `rejected`, chyba że użytkownik prosi o audyt wcześniejszych decyzji.

## Etap 2: analiza i grupowanie

Dla każdego kandydata:

1. Ustal portal na podstawie `web_documents.url`.
2. Połącz identyczne lub strukturalnie podobne linie w jeden wzorzec.
3. Policz liczbę dokumentów i portali, na których wzorzec wystąpił.
4. Sprawdź aktualne reguły:
   - `backend/data/site_rules.json`,
   - `backend/library/article_cleaner.py`,
   - `backend/data/pages_analyze/*.regex`, jeśli problem dotyczy pełnej ekstrakcji artykułu.
5. Otwórz kontekst źródłowego dokumentu lub chunku. Sama `line_text` często nie wystarcza do bezpiecznego regexu.
6. Przypisz proponowaną decyzję: `rule_added`, `already_covered`, `rejected` albo pozostaw `pending`, gdy brakuje dowodów.

Przed edycją przedstaw użytkownikowi krótki raport:

| Wzorzec | Portal | Rekordy | Proponowana decyzja | Uzasadnienie |
|---|---|---:|---|---|

Jeśli użytkownik zlecił od razu pełne wykonanie, raport może być częścią aktualizacji w trakcie pracy; nie wymaga osobnej zgody, o ile reguła jest dobrze ograniczona i testowalna.

## Etap 3: implementacja reguły

1. Utwórz feature branch.
2. Zmień właściwy plik reguł lub cleaner.
3. Dodaj test oparty na rzeczywistym przypadku z `document_removed_lines`.
4. Dodaj co najmniej jeden test, że zwykła treść artykułu pozostaje bez zmian.
5. Dla `site_rules.json` sprawdź poprawność JSON-a.
6. Uruchom testy celowane, a następnie adekwatny zestaw unit.

Typowe testy:

```powershell
cd backend
$env:PYTHONPATH='.'
.\.venv\Scripts\python.exe -m pytest tests\unit\test_site_rules_o2.py -q
.\.venv\Scripts\python.exe -m pytest tests\unit\test_article_cleaner.py -q
```

Zmiana `site_rules.json` na NAS jest odczytywana bez restartu z `/share/ContainerNew/lenie-config/site_rules.json`. Repozytorium pozostaje źródłem prawdy: zmiana produkcyjna musi również trafić do feature brancha i PR.

## Etap 4: zapis decyzji

Po przejściu testów oznacz dokładnie te rekordy, które uzasadniają wdrożoną decyzję.

Dodana reguła:

```powershell
cd backend
$env:PYTHONPATH='.'
.\.venv\Scripts\python.exe scripts\review_removed_lines.py `
  --mark 101,102,103 `
  --status rule_added `
  --reference "data/site_rules.json:o2.pl" `
  --note "Usuwanie bloku playera; test test_site_rules_o2.py"
```

Istniejąca reguła już obsługuje przypadek:

```powershell
.\.venv\Scripts\python.exe scripts\review_removed_lines.py `
  --mark 104,105 `
  --status already_covered `
  --reference "article_cleaner.py:_clean_lines_wp" `
  --note "Pokryte przez regułę dodaną w PR #NNN"
```

Kandydat odrzucony:

```powershell
.\.venv\Scripts\python.exe scripts\review_removed_lines.py `
  --mark 106 `
  --status rejected `
  --note "Tekst jest częścią artykułu; reguła powodowałaby false positive"
```

Wymagania:

- `--mark` przyjmuje identyfikatory wierszy `document_removed_lines`, nie `document_id` ani `run_id`.
- `rule_added` wymaga `--reference`.
- W `--reference` podawaj stabilną lokalizację, np. `data/site_rules.json:o2.pl` lub `article_cleaner.py:_clean_lines_wp`.
- W `--note` wpisz decyzję, zakres i test albo numer PR.
- Rekordy nieobjęte zmianą pozostają `pending`.

## Etap 5: PR, deploy i kontrola

1. Zrób commit i PR zgodnie z zasadami repozytorium.
2. Poczekaj na checki i wykonaj merge dopiero po ich przejściu.
3. Dla zmian w kodzie Pythona wdroż backend.
4. Dla samego `site_rules.json` zsynchronizuj plik na NAS; restart nie jest wymagany.
5. Zweryfikuj wynik na przykładowym dokumencie.
6. Potwierdź, że oznaczone rekordy nie pojawiają się już w `--list`.

## Kryterium ukończenia

Analiza partii jest ukończona, gdy:

- każdy rozpatrywany rekord ma świadomą decyzję albo celowo pozostaje `pending`,
- każda nowa reguła ma test regresyjny,
- baza zawiera `review_status`, `reviewed_at`, `review_note` i właściwe `rule_reference`,
- zmiany są zapisane w repozytorium,
- stan produkcyjny i repozytorium nie rozjeżdżają się.

