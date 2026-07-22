# Eksperyment myślowy: od projektu hobbystycznego do usługi komercyjnej wielu użytkowników

Status: eksperyment myślowy / materiał do nauki architektury, nie plan wdrożeniowy
Powiązane dokumenty: [docs/deployment/README.md](README.md) (co jest realne, co jest zabawą intelektualną) · [nas/storage-and-jobs-migration-plan.md](nas/storage-and-jobs-migration-plan.md) (realny plan) · [nas/multi-user-household.md](nas/multi-user-household.md) (realny plan dla kilku zaufanych użytkowników)

## 1. Po co ten dokument

Lenie AI jest projektem hobbystycznym, a jednocześnie poligonem do nauki architektury systemów. Realny, wdrażany zakres to instalacja na własnym NAS dla mnie i kilku zaufanych domowników/znajomych — opisana w [nas/storage-and-jobs-migration-plan.md](nas/storage-and-jobs-migration-plan.md) i [nas/multi-user-household.md](nas/multi-user-household.md). Tylko ten zakres powinien wpływać na to, co dziś trafia do kodu.

Ten dokument jest osobnym eksperymentem myślowym: co musiałoby się zmienić, gdyby Lenie miało stać się usługą komercyjną dla wielu, **niezaufanych wobec siebie** użytkowników (w odróżnieniu od zaufanych domowników z `nas/multi-user-household.md`) — hostowaną on-premise, w chmurze albo hybrydowo. Cel jest edukacyjny, nie wdrożeniowy: zrozumieć, czym architektonicznie różni się „działa u mnie na NAS-ie dla rodziny” od „działa jako produkt, który da się skalować i sprzedawać obcym ludziom”. Wnioski stąd nie powinny wymuszać zmian w bieżącym kodzie, dopóki nie pojawi się realna decyzja biznesowa o obsłudze niezaufanych, płacących użytkowników.

## 2. Hobby/household vs usługa komercyjna — kluczowe różnice

| Wymiar | Dziś (hobby + kilku zaufanych domowników) | Usługa komercyjna wielu niezaufanych użytkowników |
|---|---|---|
| Model własności danych | Wspólna biblioteka; `user_id` identyfikuje tylko *kto czyta*, nie *czyje jest to dane* | Jawny `owner_user_id`/`workspace_id` na każdym rekordzie domenowym i jobie, wymuszony w warstwie serwisów, z pełną izolacją |
| Uwierzytelnianie i autoryzacja | Klucz API per osoba, zaufany kontekst domowy, brak haseł | Uwierzytelnianie, rotacja tokenów, autoryzacja każdego odczytu/zapisu, testy izolacji „użytkownik A nie widzi danych B” |
| Kolejka i wykonywanie jobów | PostgreSQL + jeden worker sekwencyjny wystarcza | Priorytety, fairness, lease/heartbeat, limity per użytkownik, osobne pule CPU/IO/LLM |
| Koszty i limity | Nieistotne albo obserwowane ręcznie | Budżety per użytkownik/workspace, rozliczanie zużycia LLM/API/storage, twarde limity i kontrolowane zatrzymanie po przekroczeniu |
| Observability | Logi + ręczna diagnostyka w razie problemu | `request_id`/`job_id`/`user_id`/`workspace_id` w logach, metryki per tenant, alerty o kolejce i heartbeacie |
| Bezpieczeństwo | Zaufane środowisko domowe, mała powierzchnia ataku | Rate limiting, ochrona przed SSRF i path traversal, walidacja uploadów, audyt operacji administracyjnych, szyfrowanie |
| Dostępność i SPOF | Restart NAS-a albo kontenera jest akceptowalny | SLA, potrzeba wielu instancji API, load balancer, kontrolowane wdrożenia bez przestoju |
| Infrastruktura | Jeden host, Docker Compose | Load balancer, connection pooling (PgBouncer), ewentualnie Redis, ewentualnie orkiestrator |
| Koszt utrzymania platformy | Musi być bliski zeru — to nie generuje przychodu | Musi się bilansować z przychodem; każdy dodatkowy komponent to świadomy koszt operacyjny do uzasadnienia |
| Tempo dodawania złożoności | Dodawać dopiero, gdy przeszkadza brak (YAGNI) | Dodawać wcześniej — na podstawie prognozy skali, nie tylko bieżącego bólu |

Praktyczna konsekwencja: architektura hobby/household powinna pozostać najprostsza z możliwych ([nas/multi-user-household.md](nas/multi-user-household.md)), ale model danych powinien od początku umożliwiać późniejsze dopisanie właściciela bez migracji — to jedyny element stąd, który już dziś tanio kupuje opcjonalność na przyszłość.

## 3. Kierunek skalowania

Skalowanie odbywałoby się stopniowo, w oparciu o mierzalne sygnały (nie prewencyjnie), zaczynając od tego, co już działa dla household (`nas/multi-user-household.md`), przez kolejne, coraz cięższe wzorce infrastrukturalne (kolejka zadań, cache, load balancing), dopiero gdy realna potrzeba (liczba użytkowników, obciążenie, wymagania bezpieczeństwa) to uzasadni. Konkretna architektura docelowa i harmonogram etapów to otwarte pytanie, nie rozstrzygnięty tu plan.
