# Plan implementacji: przejście z `dynamodb_sync.py` na NAS

Status: plan wykonawczy; PR 1 i PR 2 zaimplementowane oraz wdrożone na NAS
Odbiorca: model implementacyjny pracujący małymi krokami
Zakres: etap przejściowy AWS → NAS, bez projektowania docelowej chmury aplikacyjnej
Warunek końcowy tej fazy: działający ingest/job worker oraz tymczasowy bridge AWS na NAS; opróżnienie i wyłączenie bridge'a wymaga osobnej decyzji

## 1. Cel i decyzje architektoniczne

Docelowym środowiskiem wykonania i źródłem prawdy jest NAS:

- PostgreSQL na NAS przechowuje dane aplikacyjne, joby i ich stan;
- MinIO na NAS przechowuje trwałe pliki źródłowe i potrzebne artefakty;
- aplikacja działa na NAS, a dostęp z zewnątrz pozostaje poza zakresem tej fazy;
- chmura nie uczestniczy w normalnym działaniu aplikacji;
- backup wykonywany na stację roboczą dewelopera obejmuje na razie wyłącznie PostgreSQL;
- pliki źródłowe mogą być odtworzone z AWS S3, dopóki AWS S3 pozostaje dostępne;

AWS jest elementem przejściowym:

- rozszerzenie poza siecią lokalną zapisuje dziś do DynamoDB i AWS S3;
- tymczasowy proces na NAS pobiera te dane;
- proces AWS pozostaje aktywny do czasu ręcznego opróżnienia bufora; przełączenie rozszerzenia na NAS jest osobną, późniejszą fazą.

Nie implementować teraz:

- adaptera Google Cloud do importu;
- wspólnego API synchronizacji między wieloma chmurami;
- Redis, Celery lub innego brokera;
- synchronicznego mikroserwisu HTTP do konwersji HTML;
- zapisu do chmury w ścieżce obsługi `/url_add`;
- montowania MinIO jako filesystemu.

## 2. Docelowa architektura

### 2.1. Etap przejściowy

```text
Chrome poza VPN
        |
        v
AWS DynamoDB + AWS S3
        |
        v
lenie-cloud-bridge na NAS
        |
        v
DocumentIngestService
   |                 |
   v                 v
PostgreSQL          MinIO
   |
   v
job document_prepare
   |
   v
lenie-document-worker
HTML -> Markdown -> ekstrakcja LLM
```

### 2.2. Stan tej fazy

```text
Klienci korzystający z istniejącego dostępu do NAS
        |
        v
POST /url_add na NAS
        |
        v
DocumentIngestService
   |                 |
   v                 v
PostgreSQL          MinIO
   |
   v
job document_prepare
   |
   v
lenie-document-worker

PostgreSQL + MinIO
        |
        v
backup operatorski PostgreSQL na stację roboczą dewelopera
```

`lenie-cloud-bridge` nie występuje w docelowym stanie po zakończeniu późniejszej
fazy wyłączenia AWS; w bieżącej fazie pozostaje aktywny.

## 3. Warunki zakończenia

Migracja jest zakończona dopiero, gdy wszystkie poniższe warunki są spełnione:

1. `/url_add` na NAS zapisuje surowe HTML/TXT do MinIO.
2. `/url_add` tworzy trwały job `document_prepare`.
3. `lenie-document-worker` wykonuje konwersję i ekstrakcję bez udziału komputera dewelopera.
4. Restart workera nie powoduje utraty dokumentu ani konieczności ponownego wysłania go przez klienta.
5. Bridge AWS na NAS wykonuje kontrolowany import i zapisuje wynik do PostgreSQL/MinIO.
6. Restart workera i bridge'a pozwala na bezpieczne wznowienie bez utraty danych.
7. Istnieje udokumentowana i przetestowana procedura backupu oraz odtworzenia PostgreSQL na stacji roboczej.
8. Odtworzenie plików z AWS S3 jest opisane jako zależność operacyjna, a nie jako backup aplikacji.

Punkty dotyczące opróżnienia bufora, wyłączenia schedulerów, usunięcia bridge'a
i usunięcia `dynamodb_sync.py` należą do odłożonej fazy wyłączenia AWS.

## 4. Zasady dla modelu implementacyjnego

Model ma realizować po jednym PR z sekcji 7. Nie łączyć kilku PR-ów w jedną zmianę.

Przed każdym PR-em:

1. przeczytać wszystkie pliki wymienione w sekcji „Pliki”;
2. sprawdzić aktualny `git status`;
3. nie zmieniać ani nie usuwać istniejących zmian użytkownika;
4. uruchomić wskazane testy bazowe;
5. nie łączyć się z NAS, Vault ani AWS w testach jednostkowych.

Po każdym PR-ze:

1. uruchomić wskazane testy;
2. wypisać zmienione pliki;
3. wypisać testy, których nie udało się uruchomić;
4. zatrzymać pracę i nie rozpoczynać kolejnego PR-u automatycznie.

Zakazy:

- nie hardkodować `192.168.200.7` ani ścieżek `/share/...` w kodzie Pythona;
- nie przekazywać sekretów przez `jobs.parameters`;
- nie logować nagłówków `Authorization`, `x-api-key`, `X-Vault-Token` ani wartości sekretów;
- nie wykonywać połączeń sieciowych podczas importu modułu;
- nie przesuwać watermarku po częściowym przebiegu;
- nie usuwać `dynamodb_sync.py` przed PR-em 7;
- nie zmieniać formatu żądania rozszerzenia Chrome bez osobnego testu kompatybilności.

### 4.1. Niezmienniki awaryjne

- nie zakładać transakcyjności pomiędzy PostgreSQL i MinIO;
- po awarii po zapisie MinIO, ale przed zatwierdzeniem dokumentu, musi istnieć
  ścieżka wykrycia osieroconego obiektu albo ponowienia zapisu dokumentu;
- po awarii po zatwierdzeniu dokumentu, ale przed utworzeniem joba, ponowione
  żądanie lub reconciliation musi utworzyć job;
- `ensure_document_prepare_job()` nie może traktować istniejącego joba `failed`
  jako sukcesu;
- równoległe żądania tego samego URL nie mogą utworzyć dwóch dokumentów;
- worker ma przetwarzać tylko aktualny UUID dokumentu i nie może uznać scratcha
  za źródło prawdy.

## 5. Stałe kontrakty

### 5.1. Kontrakt wejścia

Dodać moduł:

`backend/library/document_ingest_service.py`

Minimalne struktury:

```python
@dataclass(frozen=True)
class IngestRequest:
    url: str
    document_type: str
    text: str = ""
    html: str = ""
    title: str = ""
    language: str = ""
    note: str = "default_note"
    paywall: bool = False
    requires_login: bool | None = None
    social_platform: str | None = None
    source: str = "own"
    chapter_list: object = False
    byline: str = ""
    original_id: str | None = None
    published_on: object | None = None
    operation: str = "create"
    external_uuid: str | None = None
    ingested_at: object | None = None
```

```python
@dataclass(frozen=True)
class IngestResult:
    document_id: int
    status: str  # added | already_exists | refreshed
    processing_job_id: str | None
    missing_raw_html: bool = False
```

Publiczna metoda:

```python
DocumentIngestService.ingest(request: IngestRequest, initiated_by_user_id: int | None) -> IngestResult
```

Usługa:

1. nie importuje Flask;
2. dostaje `Session` i `ObjectStorage` w konstruktorze;
3. waliduje `operation` jako `create` albo `fill_missing_html`;
4. generuje UUID, jeżeli `external_uuid` nie został przekazany;
5. zachowuje UUID z AWS podczas importu przejściowego;
6. zapisuje `{uuid}.html` i `{uuid}.txt` przez `ObjectStorage`;
7. tworzy lub odświeża dokument i mapuje `text` oraz `text_raw` do bazy;
8. tworzy idempotentny job `document_prepare` dla strony z HTML;
9. zwraca wynik bez zależności od sposobu dostarczenia danych.

Status dokumentu:

- webpage/social post z przechwyconą treścią:
  `DOCUMENT_INTO_DATABASE`;
- link bez treści: `URL_ADDED`.

Rozszerzyć konstruktor `DocumentService` o opcjonalny `storage`:

```python
DocumentService(session, storage=None)
```

Zasady kompatybilności:

- jeżeli `storage` przekazano, `create_document()` i
  `fill_missing_source_html()` muszą używać dokładnie tej instancji;
- jeżeli `storage` jest `None`, istniejący kod może leniwie zbudować storage z
  konfiguracji;
- `fill_missing_source_html()` dostaje opcjonalny `external_uuid`, aby bridge
  zachował UUID źródła zamiast generować nowy;
- `DocumentIngestService` zawsze przekazuje wstrzyknięty storage;
- nie ładować konfiguracji w czasie importu modułu.

### 5.2. Klucze MinIO

W tym projekcie nie wykonywać migracji istniejących obiektów.

Zachować kompatybilne klucze źródłowe:

```text
{document.uuid}.html
{document.uuid}.txt
```

Artefakty przetwarzania zachować tymczasowo pod istniejącym prefiksem:

```text
cache/markdown/{document.id}/{filename}
```

Zmiana konwencji kluczy ma być osobnym projektem po usunięciu bridge'a AWS.

### 5.3. Job `document_prepare`

Parametry:

```json
{
  "document_id": 123,
  "document_uuid": "uuid-at-enqueue-time"
}
```

Klucz idempotencji:

```text
document_prepare:{document_id}:{document_uuid}
```

Rezultat:

```json
{
  "document_id": 123,
  "markdown_created": true,
  "llm_extracted": true,
  "artifacts_uploaded": 6
}
```

Postęp:

```json
{"phase": "materialize_source", "document_id": 123}
{"phase": "html_to_markdown", "document_id": 123}
{"phase": "llm_extract", "document_id": 123}
{"phase": "upload_artifacts", "document_id": 123}
```

Job musi być wznawialny:

- jeżeli raw markdown już istnieje w MinIO, nie konwertować HTML ponownie;
- jeżeli `text_md` jest już zapisany, zakończyć bez ponownego LLM;
- brak wyniku LLM dla webpage nie jest pełnym sukcesem joba; job ma zakończyć
  się błędem możliwym do retry, pozostawiając zapisany raw markdown;
- jeżeli zmienił się `document.uuid`, zakończyć kontrolowanym błędem jako job nieaktualny;
- scratch nie może być źródłem prawdy.

### 5.4. Job przejściowy `legacy_aws_pull`

Parametry dozwolone tylko dla klucza `service`:

```json
{
  "since": "2026-07-01T00:00:00Z",
  "dry_run": false,
  "limit": 0
}
```

Scheduler tworzy job bez parametrów. Wtedy watermark pochodzi z ostatniego pełnego sukcesu.

Klucz idempotencji schedulera:

```text
legacy_aws_pull:{UTC time bucket}
```

`limit > 0` i `dry_run=true` nigdy nie przesuwają watermarku.

## 6. Watermark i niezawodność bridge'a AWS

Nie tworzyć osobnego systemu synchronizacji dla przyszłych chmur. W etapie przejściowym nadal używać `import_logs`.

Reguły:

1. `ImportLogTracker` zaczyna przebieg przed odpytaniem DynamoDB.
2. Pusty przebieg jest pełnym sukcesem i przesuwa watermark.
3. Watermarkiem jest UTC `started_at` ostatniego pełnego sukcesu.
4. Zapytanie odejmuje konfigurowalne okno bezpieczeństwa, domyślnie 300 sekund.
5. Duplikaty są bezpiecznie rozpoznawane przez URL/UUID.
6. Jakikolwiek błąd elementu oznacza błąd całego przebiegu.
7. Po błędzie watermark nie jest przesuwany.
8. Retry ponownie czyta nakładające się okno, pomija kompletne dokumenty i dokańcza niekompletne.
9. `limit > 0` oznacza przebieg diagnostyczny i nie może mieć statusu `success`.
10. Brak poprzedniego sukcesu wymaga jawnego `since`.

Rozszerzyć `ImportLogTracker` o jawne zakończenie częściowe:

```python
tracker.mark_partial("diagnostic limit")
```

`mark_partial()` ustawia status `partial` przy poprawnym wyjściu z context
managera. Wyjątek nadal ustawia `error`. Tylko `success` może być źródłem
watermarku.

Tymczasowy bridge nie używa SSM do odkrywania zasobów. Nazwy zapisać w Vault:

```text
AWS_LEGACY_PULL_DYNAMODB_TABLE
AWS_LEGACY_PULL_S3_BUCKET
AWS_LEGACY_PULL_ENABLED
AWS_LEGACY_PULL_INTERVAL_MINUTES
AWS_LEGACY_PULL_OVERLAP_SECONDS
```

Poświadczenia AWS:

```text
AWS_LEGACY_PULL_ACCESS_KEY_ID
AWS_LEGACY_PULL_SECRET_ACCESS_KEY
AWS_LEGACY_PULL_SESSION_TOKEN  # opcjonalny
AWS_LEGACY_PULL_REGION
AWS_ACCOUNT_ID     # opcjonalna kontrola konta
```

Bridge buduje `boto3.Session` jawnie z obiektu konfiguracji. Nie polega na tym,
że Vault zmodyfikuje `os.environ`.

## 7. Kolejność implementacji

### PR 1 — wspólna usługa ingestu

### Cel

Jedna logika zapisu dla `/url_add` i przyszłego bridge'a AWS.

### Pliki

Dodaj:

- `backend/library/document_ingest_service.py`
- `backend/tests/unit/test_document_ingest_service.py`

Zmień:

- `backend/server.py`
- `backend/library/document_service.py`
- `backend/library/import_log_tracker.py`, jeżeli PR 1 przygotowuje już
  wstrzykiwanie zależności; samo `mark_partial()` można pozostawić do PR 3
- `backend/tests/unit/test_document_service.py`
- testy `/url_add`, jeżeli są w repozytorium; jeżeli ich nie ma, dodać
  `backend/tests/unit/test_url_add.py`

### Kroki

1. Dodać `IngestRequest`, `IngestResult` i `DocumentIngestService`.
2. Wstrzykiwać `Session` i `ObjectStorage`; nie wywoływać `load_config()` w konstruktorze domenowym.
3. Dodać do `DocumentService` opcjonalny storage zgodnie z sekcją 5.1.
4. Wykorzystać istniejące reguły `DocumentService.import_document()`,
   `fill_missing_source_html()` i mapowanie pól.
5. Zachować obsługę `social_media_post`.
6. Zachować status HTTP i kształt odpowiedzi `/url_add`.
7. Przenieść orkiestrację `/url_add` do nowej usługi.
8. Na tym etapie `processing_job_id` może pozostać `None`; job zostanie dodany w PR 2.
9. Nie zmieniać `popup.js`.

### Testy obowiązkowe

- utworzenie webpage z HTML i TXT;
- utworzenie linku bez HTML;
- utworzenie social media post;
- wykrycie istniejącego URL;
- `fill_missing_html`;
- odrzucenie refreshu, gdy HTML już istnieje;
- zachowanie zewnętrznego UUID;
- zapis obiektów przez fałszywy `ObjectStorage`;
- brak połączeń z Vault/AWS podczas importu modułu.

### Kryterium akceptacji

Dotychczasowe żądanie rozszerzenia daje tę samą odpowiedź i zapisuje pliki do
skonfigurowanego storage przez nową usługę.

### PR 2 — kolejka wielotypowa i osobny document worker

### Cel

Przetwarzanie HTML/LLM ma działać poza procesem Flask i poza workerem feedów.

### Pliki

Dodaj:

- migrację Alembic po aktualnym headzie;
- `backend/library/document_processing_service.py`;
- `backend/tests/unit/test_document_processing_service.py`;
- `backend/tests/unit/test_job_queue.py`;
- `backend/tests/unit/test_worker.py`.

Zmień:

- `backend/library/db/models.py`;
- `backend/library/job_queue.py`;
- `backend/worker.py`;
- `backend/library/document_ingest_service.py`;
- `backend/library/document_prepare.py`;
- `backend/library/article_pipeline.py`, tylko jeżeli wymaga wstrzyknięcia storage;
- `backend/Dockerfile`;
- `infra/docker/compose.nas.yaml`;
- `infra/docker/nas-deploy.sh`;
- `infra/docker/nas-deploy.ps1`;
- `Makefile`;
- `scripts/vars-classification.yaml`;
- `infra/docker/nas.env.example`.

### Kroki: kolejka

1. Dodać typy `document_prepare` i `legacy_aws_pull` do constraintu `jobs.type`.
2. Dodać typy do `JOB_TYPES`.
3. Zmienić `claim(session)` na `claim(session, allowed_types)`.
4. Wymagać niepustego zbioru `allowed_types`.
5. Dodać workerowi argument `--types` z listą rozdzielaną przecinkami.
6. Dodać flagę `--scheduler`.
7. Tylko istniejący `lenie-worker` uruchamia scheduler, recovery i bierze globalną
   blokadę koordynatora.
8. Workery specjalizowane nie biorą globalnej blokady; bezpieczeństwo claimu daje
   `FOR UPDATE SKIP LOCKED`.
9. Workery specjalizowane pobierają wyłącznie swoje typy.

### Kroki: przetwarzanie

1. `document_prepare.py` nie może importować `library.api.aws.s3_aws`.
2. Gdy lokalnego HTML brakuje, pobrać `{doc.uuid}.html` przez `ObjectStorage.get_bytes()`.
3. Utworzyć scratch:

   ```text
   {WORK_DIR}/document-jobs/{job_id}/{document_id}
   ```

4. Uruchomić istniejący `article_pipeline.extract_article()`.
5. Zapisać `text_extracted`, `text_md` i obrazy jak obecnie.
6. Wysłać artefakty do MinIO.
7. Usunąć scratch po sukcesie.
8. Po błędzie zachować scratch maksymalnie przez konfigurowaną retencję albo pozostawić
   go do osobnego cleanup joba; nie implementować złożonego lifecycle w tym PR-ze.
9. Wywoływać `heartbeat()` przed i po każdym etapie.
10. Sprawdzać `cancel_requested` pomiędzy etapami.
11. Dodać `ensure_document_prepare_job()` wywoływane zarówno po dodaniu
    dokumentu, jak i przy wykryciu istniejącego, niekompletnego dokumentu.
    Dzięki temu ponowione `/url_add` naprawia sytuację, w której dokument został
    zapisany, ale pierwsze utworzenie joba nie powiodło się.

### Kroki: obrazy Docker

Przygotować dwa targety lub dwa obrazy z jednego Dockerfile:

- obraz serwera/feed workera: `--extra docker`;
- obraz document workera: `--extra docker --extra markdown`.

Obraz document workera musi zawierać:

- `markitdown`;
- `html2markdown`;
- `html2text`;
- kod `library`;
- `worker.py`.

Nie tworzyć HTTP API między workerami.

### Compose

Dodać:

```text
lenie-document-worker
```

Konfiguracja:

- ta sama sieć `lenie-net`;
- ten sam plik bootstrapujący Vault;
- zależność od PostgreSQL i MinIO;
- komenda obsługująca tylko `document_prepare`;
- osobny volume `lenie-document-work:/app/work`;
- brak opublikowanych portów.

Istniejący `lenie-worker` ma jawnie obsługiwać dotychczasowe typy i scheduler.

### Kryterium akceptacji

Dodanie webpage przez `/url_add`:

1. zwraca odpowiedź bez oczekiwania na LLM;
2. tworzy job;
3. document worker pobiera HTML z MinIO;
4. zapisuje markdown i wynik LLM;
5. restart workera pozwala na kontrolowany retry.

### PR 3 — tymczasowy bridge AWS jako job na NAS

### Cel

Przenieść dotychczasowe pobieranie DynamoDB/S3 na NAS bez wykonywania
przetwarzania dokumentu w bridge'u.

### Pliki

Dodaj:

- `backend/library/legacy_aws_pull_service.py`;
- `backend/tests/unit/test_legacy_aws_pull_service.py`.

Zmień:

- `backend/imports/dynamodb_sync.py`;
- `backend/worker.py`;
- `backend/library/job_queue.py`;
- `backend/library/feed_routes.py`;
- `backend/library/import_log_tracker.py`;
- `backend/tests/unit/test_import_log_tracker.py`;
- `scripts/vars-classification.yaml`;
- `infra/docker/nas.env.example`;
- `infra/docker/compose.nas.yaml`;
- dokumentację importów.

### Kroki

1. Przenieść z `dynamodb_sync.py` do usługi wyłącznie:
   - parsowanie timestampu;
   - query `DateIndex` z paginacją;
   - pobieranie `{uuid}.html` i `{uuid}.txt`;
   - mapowanie pól DynamoDB do `IngestRequest`;
   - watermark i raportowanie.
2. Nie przenosić:
   - lokalnego zapisu cache;
   - `process_article_content`;
   - `sync_generated_cache`;
   - promptu CLI;
   - bezpośrednich zapisów dokumentu.
3. Każdy element przekazać do `DocumentIngestService`.
4. Bridge zapisuje źródła do MinIO przez usługę ingestu.
5. Przetwarzanie wykonuje później job `document_prepare`.
6. Dodać obsługę joba `legacy_aws_pull` do workera.
7. Dodać specjalizowany kontener `lenie-cloud-bridge`, obsługujący tylko ten typ.
8. Scheduler pozostaje w głównym `lenie-worker` i tylko tworzy joby.
9. `dynamodb_sync.py` pozostawić tymczasowo jako cienki wrapper nowej usługi.
10. Wrapper nie może zawierać logiki biznesowej.
11. Dodać `ImportLogTracker.mark_partial()` i użyć go dla dry-run/limit.

### Walidacja API jobów

`POST /jobs` może przyjąć `legacy_aws_pull` wyłącznie od klucza `service`.

Dozwolone parametry:

- `since`: `null` albo ISO-8601;
- `dry_run`: boolean;
- `limit`: integer `0..1000`.

Odrzucić wszystkie dodatkowe pola.

### Testy obowiązkowe

- paginacja DynamoDB;
- nakładające się okno watermarku;
- pusty pełny sukces;
- częściowy błąd bez przesunięcia watermarku;
- `limit` bez przesunięcia watermarku;
- dry-run bez DB/MinIO;
- jawne poświadczenia przekazane do `boto3.Session`;
- brak użycia poświadczeń MinIO jako poświadczeń AWS;
- create, duplicate i fill missing HTML;
- job bridge'a tworzy job dokumentu, ale sam nie uruchamia LLM.

### Kryterium akceptacji

Ręczny job na NAS pobiera kontrolowany zakres AWS i daje ten sam wynik biznesowy
co dotychczasowy skrypt, ale cała dalsza obróbka odbywa się w document workerze.

### PR 4 — scheduler, obserwowalność i panel Jobów

### Cel

Synchronizacja przejściowa i przetwarzanie mają być widoczne oraz sterowalne bez
komputera dewelopera.

### Pliki

Zmień:

- `backend/worker.py`;
- `backend/library/feed_routes.py`;
- `web_interface_react/src/modules/shared/pages/jobs.tsx`;
- odpowiednie testy backendu i frontendu;
- `docs/deployment/nas/storage-and-jobs-migration-plan.md`.

### Kroki

1. Scheduler tworzy `legacy_aws_pull` tylko przy `AWS_LEGACY_PULL_ENABLED=true`.
2. Domyślną wartością jest `false`.
3. Interwał pobierać z `AWS_LEGACY_PULL_INTERVAL_MINUTES`.
4. Idempotency key generować z przedziału UTC.
5. Nie tworzyć nowego joba, gdy istnieje `queued`, `running` albo
   `cancel_requested` tego samego typu.
6. Rozszerzyć listę Jobów o:
   - czas utworzenia, startu i końca;
   - pełny wynik licznikowy;
   - watermark;
   - przycisk retry;
   - przycisk cancel.
7. Dodać przycisk ręcznego `legacy_aws_pull` tylko jeżeli UI działa z kluczem
   service. Jeżeli UI używa klucza user, nie osłabiać autoryzacji; pozostawić
   ręczne wywołanie przez API.
8. Nie dodawać edycji nazw tabeli, bucketa ani sekretów w UI.

### Kryterium akceptacji

Operator może stwierdzić z panelu/API:

- kiedy bridge działał;
- jaki watermark zastosował;
- ile rekordów znalazł, dodał, pominął i odświeżył;
- który dokument nie został przetworzony;
- czy retry się powiódł.

### PR 5 — wdrożenie przejściowe na NAS

Ten etap obejmuje operacje wdrożeniowe. Nie wykonywać ich w ramach implementacji
bez jawnej zgody operatora.

### Kolejność

1. Zbudować i wdrożyć nowe obrazy z wyłączonym schedulerem AWS.
2. Uruchomić migracje Alembic.
3. Sprawdzić healthcheck PostgreSQL, MinIO i workerów.
4. Sprawdzić tożsamość konta AWS przez STS, jeżeli skonfigurowano `AWS_ACCOUNT_ID`.
5. Uruchomić dry-run z jawnym `since`.
6. Uruchomić realny import jednego kontrolowanego dokumentu.
7. Zweryfikować:
   - rekord dokumentu;
   - obiekty `{uuid}.html/.txt` w MinIO;
   - job `document_prepare`;
   - zapis `text_md`;
   - artefakty MinIO;
   - wpis `import_logs`.
8. Włączyć scheduler na NAS.
9. Wyłączyć lokalny harmonogram na komputerze dewelopera.
10. Obserwować co najmniej 7 dni.

### Rollback

1. Ustawić `AWS_LEGACY_PULL_ENABLED=false`.
2. Zatrzymać `lenie-cloud-bridge`.
3. Nie usuwać danych z PostgreSQL ani MinIO.
4. W razie konieczności uruchomić cienki wrapper lokalnie z jawnym `since`.
5. Po naprawie wznowić z ostatniego pełnego sukcesu.

### PR 6 — przełączenie rozszerzenia na VPN/NAS

Status: odłożone poza bieżącą fazę. VPN ani stabilny zewnętrzny dostęp do NAS
nie są skonfigurowane. Nie zmieniać `popup.js`, CORS ani adresu API w ramach
tej migracji.

Ten etap jest odłożony. Nie zmieniać rozszerzenia Chrome, konfiguracji VPN,
DNS/TLS ani cloud ingress. W bieżącej fazie testować `/url_add` wyłącznie z
istniejącego dostępu do NAS.

### PR 7 — opróżnienie AWS i usunięcie `dynamodb_sync.py`

Status: odłożone. Ten etap wymaga osobnej decyzji po uruchomieniu i obserwacji
bridge'a na NAS. Do tego czasu AWS S3 pozostaje źródłem odtworzenia plików, a
`dynamodb_sync.py` pozostaje ścieżką awaryjną.

### Warunki wejściowe

Wszystkie muszą być spełnione:

1. Cloud ingress nie przyjmuje nowych danych.
2. Ostatni pełny `legacy_aws_pull` zwrócił zero nowych elementów.
3. Po odczekaniu co najmniej jednego pełnego interwału kolejny przebieg również
   zwrócił zero.
4. Brak jobów `legacy_aws_pull` w stanie `queued`, `running` lub
   `cancel_requested`.
5. Wszystkie dokumenty z ostatniego importu mają pliki w MinIO.
6. Wszystkie wymagane `document_prepare` są `done` albo mają świadomie
   zaakceptowany błąd.
7. Rozszerzenie działa wyłącznie z NAS.
8. Backup PostgreSQL i MinIO został wykonany i testowo odtworzony.

### Pliki do usunięcia

- `backend/imports/dynamodb_sync.py`;
- `backend/tests/unit/test_dynamodb_sync_orm.py`;
- `backend/tests/unit/test_dynamodb_sync_auto_since.py`;
- `backend/library/legacy_aws_pull_service.py`;
- `backend/tests/unit/test_legacy_aws_pull_service.py`;
- `backend/library/api/aws/s3_aws.py`, ale tylko jeżeli `rg` nie pokaże innych
  użytkowników.

### Pliki do zmiany

- `backend/worker.py` — usunąć scheduler i wykonanie `legacy_aws_pull`;
- `backend/library/job_queue.py` — zablokować tworzenie nowych jobów tego typu;
- `backend/library/feed_routes.py` — usunąć możliwość wywołania;
- `infra/docker/compose.nas.yaml` — usunąć `lenie-cloud-bridge`;
- skrypty deploy — usunąć tę usługę;
- `scripts/vars-classification.yaml` — oznaczyć/usunąć zmienne `AWS_LEGACY_PULL_*`;
- Vault — usunięcie sekretów jest osobną operacją wymagającą zgody;
- dokumentacja importów i deploymentu;
- README-y wskazujące `dynamodb_sync.py` jako aktywną ścieżkę;
- `docs/storage.md` — opisać bezpośredni ingest NAS;
- ten dokument — ustawić status „zrealizowany”.

Historyczne migracje Alembic i historyczne rekordy `jobs` mogą nadal zawierać
tekst `legacy_aws_pull`. Nie przepisywać historii tylko po to, aby usunąć nazwę.
Kod `enqueue()` i API muszą jednak odrzucać tworzenie nowych jobów tego typu.

### Kontrola końcowa

Uruchomić:

```text
rg -n "dynamodb_sync|legacy_aws_pull|s3_file_exist|s3_take_file" backend docs infra
```

Dozwolone trafienia:

- historia migracji;
- dokumenty historyczne wyraźnie oznaczone jako nieaktywne;
- ten plan jako zapis migracji.

Niedozwolone trafienia:

- kod runtime;
- Compose aktywnej usługi;
- scheduler;
- instrukcja operatorska sugerująca uruchomienie starego skryptu.

## 8. Backup PostgreSQL na stację roboczą

Backup nie jest częścią `DocumentIngestService` ani document workera.

Na obecnym etapie nie implementować backupu MinIO ani backupu do chmury.
Wykonywać backup PostgreSQL na stację roboczą dewelopera, z następującym
kontraktem:

- backup jest wykonywany poza ścieżką `/url_add` i workerem;
- błąd backupu nie blokuje `/url_add`;
- PostgreSQL jest backupowany spójnym dumpem do jawnie wskazanego katalogu
  stacji roboczej;
- dump nie zawiera sekretów aplikacyjnych poza danymi, które faktycznie są
  przechowywane w bazie;
- odtworzenie dumpa jest testowane przed uznaniem backupu za działający;
- pliki MinIO są obecnie odtwarzane z AWS S3; po wyłączeniu AWS trzeba dodać
  osobny backup MinIO przed usunięciem tej zależności.

Nie dodawać `BACKUP_STORAGE_*` do aplikacji. Backup pozostaje osobnym skryptem
operatorskim lub zadaniem wykonywanym ręcznie.

## 9. Macierz testów końcowych

| Przypadek | Oczekiwany wynik |
|---|---|
| `/url_add` webpage | dokument + MinIO + queued `document_prepare` |
| `/url_add` link | dokument, bez joba HTML |
| social post | tekst zapisany bez konwersji HTML |
| duplicate URL | brak duplikatu; informacja o istniejącym dokumencie |
| fill missing HTML | nowy UUID, plik w MinIO, nowy idempotentny job |
| restart document workera | stale job wraca do kolejki i wznawia etap |
| powtórzenie document joba | brak ponownego LLM dla kompletnego dokumentu |
| pusty bridge AWS | pełny sukces i przesunięty watermark |
| błąd jednego elementu AWS | brak przesunięcia watermarku |
| bridge z `limit` | brak przesunięcia watermarku |
| awaria AWS | NAS API i document worker nadal działają |
| awaria backupu PostgreSQL | NAS API i document worker nadal działają |
| wyłączony komputer dewelopera | ingest, kolejka i processing nadal działają |

## 10. Minimalny zestaw komend weryfikacyjnych

Model implementacyjny dobiera dokładne testy do PR-u, ale nie może pominąć:

```powershell
Set-Location backend
.\.venv\Scripts\python.exe -m pytest tests\unit\test_document_ingest_service.py -q -p no:cacheprovider
.\.venv\Scripts\python.exe -m pytest tests\unit\test_document_processing_service.py -q -p no:cacheprovider
.\.venv\Scripts\python.exe -m pytest tests\unit\test_job_queue.py tests\unit\test_worker.py -q -p no:cacheprovider
.\.venv\Scripts\alembic.exe -c alembic.ini heads
```

Testy wymagające `tmp_path` muszą używać zapisywalnego `--basetemp` wewnątrz
repozytorium. Testy jednostkowe muszą ustawiać backend konfiguracji na testowy/env
przed importem modułu, aby nigdy nie próbowały łączyć się z Vault.

Przed wdrożeniem:

```powershell
docker compose -f infra/docker/compose.nas.yaml config
```

Budowanie, push do registry, migracje na NAS, zapis do Vault, wyłączenie cloud
ingress i usunięcie sekretów są operacjami zewnętrznymi. Model nie wykonuje ich
bez jawnej zgody użytkownika.

## 11. Szablon zlecenia pojedynczego PR-u tańszemu modelowi

Przekazywać modelowi tylko jeden etap:

```text
Zaimplementuj wyłącznie PR <numer> z:
docs/deployment/nas/dynamodb-sync-to-nas-implementation-plan.md

Najpierw przeczytaj cały plan oraz wszystkie pliki wymienione dla tego PR-u.
Nie rozpoczynaj następnego PR-u. Nie wykonuj operacji na NAS, AWS ani Vault.
Nie zmieniaj istniejących zmian użytkownika. Po implementacji uruchom testy
wskazane dla PR-u i podaj:
1. listę zmienionych plików,
2. wynik testów,
3. niewykonane testy i powód,
4. ryzyka lub decyzje wymagające zatwierdzenia.
```

Jeżeli model napotka sprzeczność między planem a aktualnym kodem, ma zatrzymać
się po diagnostyce i opisać sprzeczność. Nie może samodzielnie rozszerzać zakresu
na kolejny PR.
