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

## 3. Etapy i wzorce skalowania

Zakładany punkt startowy: `nas/multi-user-household.md` — jeden worker, PostgreSQL Queue, kilku zaufanych użytkowników, właściciel joba już zapisywany. Kolejne elementy poniżej należy dodawać dopiero po osiągnięciu mierzalnych progów (sekcja 3.10), a nie prewencyjnie.

### 3.1. Etap B — kilku niezaufanych użytkowników, nadal PostgreSQL Queue

PostgreSQL może nadal obsługiwać kolejkę przy kilku użytkownikach i umiarkowanej liczbie zadań. Można uruchomić kilka workerów pobierających rekordy przez `FOR UPDATE SKIP LOCKED`.

Potrzebne rozszerzenia:

- priorytet joba;
- właściciel/workspace joba;
- heartbeat oraz lease z terminem wygaśnięcia;
- kontrolowane retry z backoff;
- idempotency key;
- limity współbieżności globalne, per typ i per użytkownik;
- fairness, aby jeden użytkownik nie blokował całej kolejki;
- osobne pule dla zadań CPU, IO oraz kosztownych wywołań LLM;
- timeout i możliwość anulowania;
- deduplikacja równoważnych zadań;
- limit rozmiaru parametrów i rezultatów przechowywanych w JSONB.

Przykładowe limity:

- maksymalna liczba aktywnych jobów użytkownika;
- maksymalny rozmiar uploadu;
- miesięczny budżet LLM/transkrypcji;
- liczba równoległych transkrypcji;
- przestrzeń durable i checkpoint;
- maksymalny czas życia joba oraz scratch.

Model danych z pełnym `owner_user_id`/`workspace_id`, rolami i izolacją (`workspaces`, `organizations`, Row-Level Security) opisany jest w [nas/multi-user-household.md — sekcja o granicy household vs workspace](nas/multi-user-household.md).

### 3.2. Kiedy wprowadzić Redis

Redis ma sens, gdy wystąpi co najmniej kilka z poniższych problemów:

- bardzo częste odpytywanie PostgreSQL o nowe joby;
- potrzeba dostarczania postępu w czasie rzeczywistym do wielu klientów;
- duża liczba krótkich zadań;
- potrzeba szybkich liczników, rate limiting i rozproszonych blokad;
- wiele instancji API wymagających współdzielonego cache;
- presja kolejki zaczyna wpływać na zapytania biznesowe PostgreSQL;
- potrzebne są krótkotrwałe dane, których nie warto zapisywać w bazie trwałej.

Redis może pełnić różne role:

- broker kolejki;
- pub/sub dla zdarzeń postępu;
- cache odpowiedzi;
- rate limiter;
- magazyn krótkotrwałych sesji lub tokenów unieważnienia;
- rozproszone semafory limitujące kosztowne usługi.

Redis nie powinien być jedynym źródłem prawdy dla historii jobów. Trwały status, parametry, wynik, koszt i audyt pozostają w PostgreSQL.

### 3.3. Wybór systemu kolejki po PostgreSQL

Najbardziej prawdopodobny wariant dla obecnego stosu Python:

```text
API -> PostgreSQL (rekord i historia joba)
    -> Redis (broker)
    -> Celery workers
```

Celery zapewnia routing do kolejek, retry, harmonogram Celery Beat, limity i skalowanie workerów. Kosztem jest większa złożoność konfiguracji, trudniejsza semantyka dokładnie-jeden-raz oraz potrzeba świadomego projektowania idempotencji.

Alternatywy do oceny przed decyzją:

- Dramatiq + Redis — prostszy model niż Celery, mniej funkcji;
- RQ + Redis — bardzo prosty, dobry dla nieskomplikowanych kolejek;
- Temporal — trwałe workflow, retry i długie procesy, ale znacznie większa złożoność operacyjna;
- chmurowe kolejki: AWS SQS, Google Cloud Tasks albo Pub/Sub — mniej infrastruktury własnej, lecz większe związanie z dostawcą;
- Kubernetes Jobs — dobre dla ciężkich, izolowanych zadań, ale nie zastępują same w sobie kompletnego modelu workflow.

Decyzja powinna wynikać z pomiarów i charakteru zadań. Dla długich procesów wieloetapowych z oczekiwaniem na zewnętrzne zdarzenia Temporal może być lepszy niż rozbudowywanie Celery. Dla zwykłych importów i analiz Celery lub Dramatiq powinny wystarczyć.

### 3.4. Podział kolejek i workerów

Przy większej skali należy rozdzielić zadania według charakterystyki:

```text
queue: io          pobieranie stron, importy, storage
queue: cpu         konwersje, lokalne modele, OCR
queue: media       YouTube, audio, transkrypcje
queue: llm         analizy i generowanie treści
queue: embedding   embeddingi i operacje wektorowe
queue: maintenance cleanup, migracje, backupy
```

Każda kolejka może mieć:

- inną liczbę workerów;
- inne limity CPU i RAM;
- osobny timeout;
- inną politykę retry;
- limit zewnętrznego API;
- osobny priorytet;
- kontrolę maksymalnego kosztu.

Ciężkie zadania nie powinny blokować krótkich operacji interaktywnych.

### 3.5. Skalowanie API

Po przejściu na wiele instancji API:

- API musi być bezstanowe;
- sesje nie mogą zależeć od pamięci pojedynczego procesu;
- wszystkie instancje korzystają z tej samej bazy i kolejki;
- pliki trafiają bezpośrednio do object storage lub przez kontrolowany streaming;
- postęp jest dystrybuowany przez Redis pub/sub, SSE albo WebSocket gateway;
- reverse proxy/load balancer obsługuje TLS i routing;
- migracje bazy wykonuje jeden kontrolowany proces wdrożeniowy;
- zadania okresowe mają pojedynczego lidera albo dedykowany scheduler.

Do uploadu dużych plików warto wykorzystać krótkotrwałe presigned URLs. API autoryzuje operację i rejestruje oczekiwany obiekt, ale nie musi przesyłać wszystkich bajtów przez własny proces.

### 3.6. Skalowanie PostgreSQL

Kolejne kroki, dopiero gdy są potrzebne:

1. indeksy wynikające z rzeczywistych zapytań;
2. connection pooling, np. PgBouncer;
3. limity połączeń API i workerów;
4. oddzielenie analitycznych lub ciężkich zapytań;
5. read replica dla odczytów, jeżeli aplikacja potrafi zaakceptować opóźnienie replikacji;
6. partycjonowanie dużych tabel logów i zdarzeń;
7. polityka archiwizacji jobów i logów;
8. zarządzana baza w chmurze przy przejściu na AWS/GCP.

Nie należy przenosić spójnego stanu domenowego do Redis tylko po to, aby odciążyć bazę. Najpierw trzeba zmierzyć i zoptymalizować konkretne zapytania.

### 3.7. Skalowanie object storage

Object storage naturalnie skaluje się lepiej niż współdzielony filesystem, ale aplikacja musi uwzględniać:

- wiele równoległych uploadów i multipart upload;
- checksumy;
- lifecycle i retencję per prefiks;
- limity przestrzeni per workspace;
- wersjonowanie i soft delete;
- audyt dostępu;
- regionalność danych;
- koszty transferu między workerem a storage;
- skanowanie uploadów i walidację typów plików;
- usuwanie osieroconych obiektów po nieudanych transakcjach.

Worker i storage powinny znajdować się w tej samej sieci/lokalizacji. W chmurze należy unikać transferu między regionami.

### 3.8. Limity, koszty i rozliczanie użytkowników

Każdy job powinien umożliwiać przypisanie zużycia do użytkownika lub workspace:

- czas CPU/GPU;
- liczba i czas wywołań zewnętrznych API;
- tokeny i koszt LLM;
- koszt transkrypcji;
- bajty durable/checkpoint;
- transfer;
- liczba operacji object storage;
- czas wykonania i liczba retry.

Budżet powinien być sprawdzany przed zleceniem i w trakcie długiego joba. Przekroczenie limitu nie może pozostawić niespójnego stanu; job powinien zakończyć się kontrolowanym statusem.

### 3.9. Observability dla wielu użytkowników

Minimalny zestaw:

- ustrukturyzowane logi z `request_id`, `job_id`, `user_id` i `workspace_id`;
- metryki długości i wieku kolejek;
- czas wykonania i odsetek błędów per typ joba;
- zużycie CPU, RAM i dysku scratch;
- liczba retry oraz osieroconych jobów;
- dostępność PostgreSQL, Redis i object storage;
- koszt LLM/API per użytkownik oraz job;
- alerty o braku heartbeat, rosnącej kolejce i kończącym się miejscu.

Przy większej skali można użyć OpenTelemetry oraz stosu Prometheus/Grafana/Loki albo zarządzanych odpowiedników AWS/GCP. Należy unikać umieszczania treści dokumentów i sekretów w logach oraz trace'ach.

### 3.10. Bezpieczeństwo wieloużytkownikowe

Przed zaproszeniem drugiego **niezaufanego** użytkownika (w odróżnieniu od zaufanych domowników) wymagane są co najmniej:

- poprawne uwierzytelnianie i rotacja tokenów;
- autoryzacja każdego odczytu i zapisu;
- izolacja danych per workspace;
- brak bezpośredniego dostępu użytkownika do kluczy MinIO/S3/GCS;
- krótkotrwałe presigned URLs ograniczone do konkretnego klucza i operacji;
- rate limiting API i jobów;
- walidacja uploadów oraz ochrona przed path traversal;
- ochrona przed SSRF w jobach pobierających URL;
- limity rozmiaru, czasu i liczby przekierowań;
- szyfrowanie połączeń oraz danych trwałych;
- audyt operacji administracyjnych;
- testy wykazujące, że użytkownik A nie może odczytać danych użytkownika B.

### 3.11. Progi przejścia między etapami

Przykładowe sygnały, nie sztywne wartości:

| Sygnał | Następny krok |
|---|---|
| Jeden worker nie nadąża, ale baza działa prawidłowo | Dodać workery PostgreSQL Queue |
| Ciężkie joby blokują krótkie | Rozdzielić pule/kolejki |
| Polling i claim obciążają bazę | Rozważyć Redis jako broker |
| Potrzebny realtime dla wielu klientów | Redis pub/sub + SSE/WebSocket |
| Retry i routing stają się rozbudowane | Celery albo Dramatiq |
| Workflow trwa dni i ma wiele oczekiwań/kompensacji | Ocenić Temporal |
| API ogranicza przepustowość uploadów | Presigned URLs |
| Liczba połączeń do PostgreSQL rośnie | PgBouncer i limity puli |
| Różne joby wymagają innych zasobów | Osobne typy workerów/kontenery |
| Pojedynczy host jest ograniczeniem lub SPOF | Orkiestrator/chmura i wiele węzłów |

### 3.12. Docelowy wariant wieloużytkownikowy

Możliwa architektura po osiągnięciu większej skali:

```text
                 load balancer
                       |
               +-------+-------+
               |               |
             API 1           API N
               |               |
               +-------+-------+
                       |
            PostgreSQL + PgBouncer
                       |
          trwały stan, historia, audyt

API -> Redis broker/pub-sub -> kolejki workerów
                              |- IO workers
                              |- CPU/media workers
                              |- LLM workers
                              `- maintenance workers

wszyscy -> S3/GCS/MinIO-compatible durable storage
```

Na AWS odpowiednikami mogą być zarządzany PostgreSQL, ElastiCache Redis, ECS/EKS, S3 i ewentualnie SQS. Na Google Cloud: Cloud SQL, Memorystore, Cloud Run/GKE, GCS i ewentualnie Cloud Tasks/Pub/Sub. Warstwa domenowa nie powinna zależeć od konkretnego zestawu usług. Konkretne środowiska docelowe (hiperskalerzy, chmury europejskie, on-prem enterprise) są rozwijane osobno w [docs/deployment/hyperscalers/](hyperscalers/), [docs/deployment/eu_cloud/](eu_cloud/) i [docs/deployment/onprem/](onprem/).

### 3.13. Kolejność przygotowania do obsługi niezaufanych użytkowników

1. Uszczelnić autoryzację i testy izolacji (rozszerzyć własność danych z household na pełny workspace).
2. Dodać limity oraz pomiar kosztów per użytkownik.
3. Uogólnić PostgreSQL Queue i uruchomić kilka workerów.
4. Rozdzielić kolejki według rodzaju obciążenia.
5. Dodać Redis dopiero dla zidentyfikowanej roli.
6. Wybrać Celery/Dramatiq/Temporal lub usługę chmurową na podstawie pomiarów.
7. Skalować API i bazę po usunięciu wąskich gardeł aplikacyjnych.
8. Wprowadzić orkiestrator dopiero, gdy pojedynczy host przestanie wystarczać.

Punkt wyjścia (właściciel jobów, model household) jest już przygotowany w [nas/multi-user-household.md](nas/multi-user-household.md); reszta tej listy to praca, którą warto zrobić dopiero po realnej decyzji biznesowej. Redis, Celery i Kubernetes można dołożyć później — najdroższa byłaby migracja danych bez informacji o właścicielu, a tej już unikamy.
