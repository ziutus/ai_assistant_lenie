# Plan: kilku zaufanych użytkowników na NAS (household)

Status: **realny plan, wdrażany teraz** — w odróżnieniu od [../commercial-multi-tenant-scaling-experiment.md](../commercial-multi-tenant-scaling-experiment.md), który jest czystym eksperymentem myślowym.  
Powiązane dokumenty: [storage-and-jobs-migration-plan.md](storage-and-jobs-migration-plan.md) · [../federation-experiment.md](../federation-experiment.md)

## 1. Cel i dwa poziomy zaufania

Lenie na NAS ma obsługiwać nie tylko mnie, ale też inne osoby — w dwóch różnych rolach:

1. **Zaufani domownicy/znajomi** — pełny dostęp do wspólnej biblioteki, jak dziś. Bez planowania wydajności pod skalę.
2. **Goście read-only** — osoby, którym chcę udostępnić *wynik* mojej pracy (obrobione, oczyszczone z reklam artykuły + przeszukiwanie bazy wiedzy), ale które nie mają powodu przechowywać u mnie własnych danych ani niczego zmieniać.

To nie jest wersja okrojona planu komercyjnego — to świadomie inny model bezpieczeństwa niż izolacja per-workspace: **wspólna biblioteka dokumentów, zróżnicowany poziom zaufania per rola, brak izolacji danych między pełnymi użytkownikami**. Rola 1 jest dokładnie tym, co dziś opisuje docstring `User` w kodzie (`backend/library/db/models.py`): „Reader identity (household trust model). (...) no passwords.” Rola 2 (read-only) jest nowym wymaganiem, opisanym w sekcji 4.

Granicę, kiedy ten model przestaje wystarczać (np. gdy ktoś niezaufany chce zapisu), opisuje sekcja 6.

## 2. Co już działa dzisiaj (stan kodu, nie plan)

- Tabele `users` i `api_keys` (`kind='user'` niesie `user_id`, `kind='service'` — pełny dostęp bez tożsamości czytelnika) — `backend/library/auth.py`, `backend/library/db/models.py`.
- `GET/POST /users` (`backend/library/reader_routes.py`) — lista i tworzenie użytkownika (`username`, opcjonalny `display_name`).
- `GET/POST /api_keys`, `DELETE /api_keys/<id>` (`backend/library/api_key_routes.py`) — tworzenie/dezaktywacja kluczy; klucz `kind=user` wymaga `user_id`. Plaintext klucza (`lk_usr_...`) pokazywany jest tylko raz przy tworzeniu.
- `GET /whoami` — sprawdzenie tożsamości bieżącego klucza.
- CLI alternatywa: `imports/api_key_admin.py`.
- `UserReadingProgress`, `UserDocumentNote` — postęp czytania i notatki są **per-user**, mimo że sama biblioteka dokumentów jest wspólna.
- Rozróżnienie `kind` jest już dziś egzekwowane per-endpoint w kodzie, nie tylko w UI (`reader_routes._require_user` odrzuca klucze `service` z 403) — to jest wzorzec, na którym oprzeć rolę read-only.

Wniosek: **dodanie nowej osoby (pełnej) do systemu to już dziś dwa wywołania API** (`POST /users`, `POST /api_keys`). Rola read-only wymaga dodatkowej pracy opisanej niżej.

## 3. Czego brakuje i warto dodać teraz (tanie, bez kolejek/Redis)

1. **`initiated_by_user_id` (opcjonalny) na jobach.** Dziś `document_analysis_jobs` i przyszła wspólna tabela jobów z Etapu 2 ([storage-and-jobs-migration-plan.md, sekcja 6](storage-and-jobs-migration-plan.md#6-kolejka-i-wykonywanie-jobów)) nie wiążą joba z osobą, która go uruchomiła. Kolumna jest tania dziś (nullable FK) i pozwala odpowiedzieć na „kto to uruchomił” bez migracji danych później.
2. **`user_id` (opcjonalny) na `llm_usage_logs`.** Sprawdzone w kodzie: tabela nie ma dziś żadnej kolumny wiążącej wywołanie LLM z użytkownikiem — koszt nie jest przypisywalny do osoby. To jedyne miejsce, gdzie brak tej kolumny może realnie zaboleć: gdy ktoś zapyta „ile kosztowało to, co odpaliła osoba X w tym miesiącu”, bez tej kolumny trzeba by odtwarzać to z korelacji `request_id`/czasu — dodanie kolumny teraz jest tanie, doganianie później nie.
3. **(opcjonalnie, UX)** Prosty ekran we frontendzie: lista domowników + przycisk „dodaj klucz”, zamiast ręcznego `curl`/CLI. Nie blokuje niczego — czysto kosmetyczne.

Nic z tego nie wymaga Redis, Celery, priorytetów kolejki ani budżetów — to są kroki z eksperymentu komercyjnego, nie stąd.

## 4. Wymagania funkcjonalne: goście read-only

**Status: wyłącznie wymagania — świadomie NIE zaimplementowane.** Poniżej jest specyfikacja tego, co ma robić rola read-only, żeby dało się ją zaprojektować dobrze za pierwszym razem, a nie dopisywać uprawnienia po fakcie.

### 4.1. Kontekst i motywacja

Znajomi raczej nie będą chcieli trzymać własnych danych w mojej instancji, ale chcę móc udostępnić im efekt mojej pracy: artykuły oczyszczone z reklam/szumu (`text_md` po `article_cleaner.py`) i przeszukiwanie zgromadzonej bazy wiedzy (`/search`). To inny przypadek użycia niż domownik — read-only gość nie potrzebuje własnego postępu czytania per se, ale może z niego skorzystać, jeśli już istnieje (`UserReadingProgress`/`UserDocumentNote` działają identycznie dla obu ról — to tanie i osobiste, nie kosztuje nic dodatkowego).

### 4.2. Co gość read-only MOŻE robić

- Przeglądać dokumenty i ich oczyszczoną treść (`/document/<id>`, widok czytnika, rozdziały).
- Korzystać z `/search` — **w tym wariantu wspomaganego LLM** (parser zapytań naturalnego języka). To jedyny koszt zewnętrzny, na który się godzę dla tej roli.
- Przeglądać tagi, kolekcje, encje (NER), oś czasu wydarzeń — wszystko co jest odczytem już policzonych/zapisanych danych.
- Mieć własny, prywatny postęp czytania i notatki (już działa dla `kind=user`, tanie).

### 4.3. Czego gość read-only NIE MOŻE robić

Zasada ogólna z prośby: **wszystko, co kosztuje realne pieniądze poza samym zapytaniem wyszukiwania wspomaganego LLM, musi być zablokowane na poziomie roli**, nie tylko ukryte w UI. Konkretnie zablokowane:

- dodawanie/edycja/usuwanie dokumentów (`/url_add`, `/website_save`, `/website_delete` i pochodne);
- wyzwalanie importów i pipeline'u (`documents_pipeline`, `dynamodb_sync`, przyszłe joby z Etapu 2);
- wyzwalanie transkrypcji (AssemblyAI, płatne — patrz `ADR-011`, `TRANSCRIPTION_BALANCE_USD`);
- wyzwalanie/ponowne generowanie embeddingów;
- wyzwalanie analizy chunków, tagowania LLM, ekstrakcji encji/NER, ekstrakcji wydarzeń/okresów/tonu — wszystko, co woła `ai_ask()`/`get_embedding()` poza samym `/search`;
- zarządzanie użytkownikami i kluczami API (`/users`, `/api_keys`);
- wgląd w koszty/rozliczenia innych osób.

### 4.4. Wymóg audytu — monitorowanie aktywności gościa

Każde żądanie roli read-only musi być logowalne, żeby dało się odpowiedzieć na pytanie „co ta osoba robiła w mojej instancji”: jaki endpoint, kiedy, jaki dokument/zapytanie wyszukiwania. To wykracza poza dzisiejszy `last_used_at` na `api_keys` (nadpisywany, bez historii, patrz `library/auth.py:_touch_last_used`) — potrzebny osobny log zdarzeń per-request, przynajmniej dla tej roli. Dla pełnych domowników taki log nie jest wymagany (są zaufani z definicji), ale nic nie stoi na przeszkodzie, by ten sam mechanizm objął też ich później.

### 4.5. Model uprawnień — co to oznacza dla `AuthContext`

Dzisiejszy `AuthContext.kind` ma dwie wartości (`user`, `service`) i nie ma miejsca na trzeci poziom zaufania. Do rozstrzygnięcia przy projektowaniu (nie teraz): trzeci `kind` (np. `guest`) vs. pole `role`/`can_write` na `User` albo na `ApiKey` (ten drugi wariant pozwala jednej osobie mieć zarówno klucz pełny, jak i klucz do udostępnienia dalej — wygodniejsze dla „wyślij znajomemu klucz tylko do czytania”). Egzekwowanie musi być scentralizowane (jeden punkt sprawdzenia roli per endpoint, analogicznie do `_require_user`), żeby nowy endpoint nie „zapomniał” dodać blokady.

## 5. Co świadomie NIE jest robione teraz

Celowo pomijane, dopóki nie zajdzie realna potrzeba (patrz sekcja 6):

- `workspaces`/`organizations`, role `owner`/`admin`/`member`/`viewer`;
- Row-Level Security w PostgreSQL;
- limity/budżety per użytkownik z twardym zatrzymaniem;
- priorytety, fairness i osobne pule CPU/IO/LLM w kolejce;
- rate limiting i ochrona przed nadużyciem przez niezaufanego użytkownika;
- presigned URLs ograniczone do właściciela obiektu;
- synchronizacja/federacja między instancjami Lenie AI (patrz [../federation-experiment.md](../federation-experiment.md) — osobny, wczesny eksperyment myślowy).

Wszystko to (poza federacją) jest opisane w [../commercial-multi-tenant-scaling-experiment.md](../commercial-multi-tenant-scaling-experiment.md) — świadomie tam, a nie tutaj.

## 6. Granica: kiedy household przestaje wystarczać

| Sygnał | Co to znaczy | Gdzie szukać dalej |
|---|---|---|
| Ktoś niezaufany (poza rodziną/znajomymi) chce dostępu z prawem zapisu | Model „wspólna biblioteka” przestaje być bezpieczny | `../commercial-multi-tenant-scaling-experiment.md`, sekcja 2 i 3.1 (workspace, izolacja) |
| Ktoś zaczyna generować nieproporcjonalnie duże koszty LLM/transkrypcji | Potrzebne limity/budżety per użytkownik | tamże, sekcja 3.8 |
| Kilka osób jednocześnie zajmuje jedynego workera na długo | Potrzeba więcej niż jednego workera i fairness | tamże, sekcja 3.1 |
| Ktoś chce mieć swoją *prywatną* (nie wspólną) bibliotekę dokumentów | To już inny produkt niż „wspólna biblioteka rodzinna” | tamże, sekcja 3.1 (pełny `owner_user_id`/`workspace_id`) |
| Chcę wymieniać dokumenty/tagi z inną instancją Lenie AI (moją drugą albo znajomego) | To osobna oś od liczby użytkowników w jednej instancji | [../federation-experiment.md](../federation-experiment.md) |

Dopóki żaden z tych sygnałów się nie pojawił, sekcje 3 i 4 powyżej to całość potrzebnej specyfikacji.

## 7. Checklist wdrożenia

1. Migracja: `user_id` (nullable FK do `users.id`, `ON DELETE SET NULL`) na `llm_usage_logs`.
2. Migracja: `initiated_by_user_id` (nullable FK do `users.id`) na `document_analysis_jobs` oraz uwzględnienie tego pola w projekcie wspólnej tabeli jobów (Etap 2 głównego planu).
3. Przekazywanie `user_id` z `AuthContext` (już dostępnego w każdym żądaniu — `library/auth.py`) do miejsc tworzących joby i wywołań LLM.
4. Opcjonalnie: prosty ekran frontendowy do zarządzania domownikami (lista + dodawanie klucza), korzystający z istniejących `/users` i `/api_keys`.
5. *(świadomie odłożone — dopiero projektowanie, nie implementacja)* Rola read-only: trzeci poziom w `AuthContext`, centralna lista dozwolonych endpointów per rola, tabela audytu żądań dla tej roli — patrz sekcja 4.

To wyczerpuje realny zakres „kilku użytkowników” — reszta jest w eksperymencie myślowym albo w osobnym otwartym pytaniu o federację.
