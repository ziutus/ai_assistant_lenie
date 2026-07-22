# Plan centralizacji storage i jobów na NAS

Status: propozycja do przemyślenia  
Cel dokumentu: opisać docelową architekturę, warianty i etapy migracji bez podejmowania jeszcze ostatecznej decyzji.

Zakres: instalacja na własnym NAS — projekt hobbystyczny i edukacyjny, realnie używany, docelowo także przez kilku zaufanych domowników/znajomych (patrz [multi-user-household.md](multi-user-household.md)). Ten dokument i cały katalog [docs/deployment/nas/](.) to jedyna gałąź, która faktycznie jest wdrażana. Pozostałe katalogi w [docs/deployment/](../README.md) (hyperscalers, eu_cloud, onprem) oraz [eksperyment myślowy o skali komercyjnej](../commercial-multi-tenant-scaling-experiment.md) to nauka architektury w wolnym czasie — nie mają wpływu na bieżące decyzje kodowe poza jednym: nie zamykać sobie do nich drogi bez potrzeby (patrz [docs/deployment/README.md](../README.md)).

## 1. Cel

Docelowo NAS ma być jedynym miejscem wykonywania procesów i przechowywania danych instalacji domowej. Komputer oraz telefon mają działać wyłącznie jako klienci interfejsu WWW.

Rozwiązanie powinno jednocześnie umożliwiać późniejsze przeniesienie do AWS albo Google Cloud bez przepisywania pipeline'ów.

Docelowe wymagania:

- wszystkie importy, konwersje, analizy, transkrypcje i embeddingi działają w kontenerach;
- zadania można uruchamiać i obserwować przez API oraz WWW;
- żaden cykliczny ani ręczny proces nie zależy od komputera deweloperskiego;
- trwałe pliki mają jedno źródło prawdy;
- przerwany job można ponowić po restarcie kontenera lub NAS;
- lokalna instalacja Compose nadal działa bez obowiązkowego MinIO;
- zmiana MinIO na AWS S3 albo Google Cloud Storage nie wpływa na logikę biznesową.

## 2. Docelowa topologia

```text
telefon / komputer
        |
        v
   interfejs WWW
        |
        v
     API na NAS
        |
        v
kolejka jobów w PostgreSQL
        |
        v
 worker lub grupa workerów
      /             \
     v               v
object storage    scratch workera
MinIO/S3/GCS      lokalny dla środowiska wykonania
```

API przyjmuje żądania i zapisuje joby, ale nie powinno wykonywać długich operacji we własnym procesie. Worker pobiera zadania z trwałej kolejki, raportuje postęp i zapisuje wyniki.

## 3. Klasy danych

Podział jest logiczny. Nie oznacza, że zawsze potrzebne są dwa trwałe systemy przechowywania.

### 3.1. Durable

Trwałe dane będące źródłem prawdy:

- źródłowe HTML, TXT, PDF, audio i wideo;
- końcowy markdown, jeżeli jego ponowne uzyskanie jest kosztowne;
- rezultaty analiz potrzebne poza bazą danych;
- eksporty i pliki użytkownika;
- artefakty niezbędne do odtworzenia albo wznowienia procesu.

Miejsce przechowywania:

- NAS: MinIO;
- AWS: S3;
- Google Cloud: Cloud Storage;
- lokalny Compose: lokalny katalog lub volume przez ten sam interfejs aplikacyjny.

### 3.2. Checkpoint

Pośrednie rezultaty, które można odtworzyć, ale byłoby to drogie lub czasochłonne:

- pobrane duże pliki;
- części długiej transkrypcji;
- wynik kosztownej konwersji;
- wynik zewnętrznego API lub LLM, którego nie warto ponownie wywoływać.

Checkpoint może być zapisany w object storage i objęty polityką retencji.

### 3.3. Scratch

Pliki robocze możliwe do ponownego wygenerowania:

- rozpakowane dane;
- tymczasowe pliki konwersji;
- części pobieranego pliku;
- cache bibliotek;
- krótkotrwałe pliki pośrednie pipeline'u.

Scratch jest zwykłym filesystemem dostępnym dla workera. Na NAS może to być Docker volume albo bind mount; w chmurze dysk efemeryczny kontenera, poda albo maszyny.

Scratch nie jest źródłem prawdy. Po zakończeniu joba powinien być usuwany, z opcjonalnym zachowaniem po błędzie przez ograniczony czas.

## 4. Dlaczego nie używać object storage jako filesystemu roboczego

MinIO, S3 i GCS są magazynami obiektowymi, a nie klasycznymi filesystemami:

- katalogi są tylko prefiksami kluczy;
- zmiana części pliku zwykle wymaga zapisania całego obiektu;
- biblioteki oczekujące `Path` i `open()` wymagają lokalnej ścieżki;
- każda operacja jest wywołaniem sieciowym;
- wiele małych plików zwiększa opóźnienia i koszty operacji w chmurze;
- warstwy FUSE mają odmienną semantykę i utrudniają diagnozowanie problemów.

Rekomendowany cykl joba:

```text
1. Pobierz wejście z object storage.
2. Utwórz /work/jobs/{job_id}.
3. Wykonaj pipeline na zwykłych plikach.
4. Wyślij durable/checkpoint do object storage.
5. Zapisz rezultat i status w PostgreSQL.
6. Usuń scratch albo zachowaj go czasowo po błędzie.
```

## 5. Warstwa abstrakcji storage

Interfejs aplikacji powinien być neutralny wobec dostawcy:

```text
ObjectStorage
|- LocalObjectStorage
|- S3ObjectStorage       (AWS S3 i MinIO)
`- GCSObjectStorage      (natywny klient Google)
```

Minimalny kontrakt:

```python
put(key, stream, metadata=None)
get(key)
exists(key)
delete(key)
list(prefix)
stat(key)
materialize(key, work_dir)
```

Do rozważenia:

- przesyłanie strumieniowe zamiast ładowania całych obiektów do pamięci;
- checksumy i idempotentne zapisy;
- wersjonowanie obiektów;
- szyfrowanie;
- presigned URLs dla uploadu/downloadu przez przeglądarkę;
- jednolita konwencja kluczy, np. `documents/{uuid}/source.html` oraz `jobs/{job_id}/artifacts/...`.

## 6. Kolejka i wykonywanie jobów

Repozytorium zawiera już wzorzec `document_analysis_jobs`:

- trwałe statusy w PostgreSQL;
- postęp i błąd;
- odzyskiwanie po restarcie;
- blokadę koordynatora;
- pobieranie zadań z `FOR UPDATE SKIP LOCKED`.

Pierwszy wariant nie wymaga Redis ani Celery. Mechanizm można uogólnić do wspólnej tabeli jobów i osobnego kontenera `lenie-worker`.

Przykładowe typy jobów:

- `dynamodb_sync`;
- `documents_pipeline`;
- `youtube_processing`;
- `document_analysis`;
- `embedding`;
- `storage_migration`;
- `cache_cleanup`;
- `backup`.

Minimalne pola joba:

- `id`;
- `type`;
- `status`: `queued`, `running`, `done`, `failed`, opcjonalnie `cancel_requested`, `cancelled`;
- `parameters` JSONB;
- `progress` i opcjonalny procent;
- `result` JSONB;
- `error`;
- `attempt` i `max_attempts`;
- `created_at`, `started_at`, `heartbeat_at`, `finished_at`;
- opcjonalny użytkownik inicjujący;
- opcjonalny klucz idempotencji.

## 7. API i interfejs WWW

Proponowane API:

- `POST /jobs` — utworzenie joba;
- `GET /jobs` — historia i filtrowanie;
- `GET /jobs/{id}` — status, postęp i rezultat;
- `POST /jobs/{id}/retry` — ponowienie;
- `POST /jobs/{id}/cancel` — żądanie anulowania;
- opcjonalnie Server-Sent Events albo WebSocket do aktualizacji postępu.

Ekran „Zadania” powinien umożliwiać:

- uruchomienie importu lub pipeline'u;
- podanie bezpiecznego zestawu parametrów;
- obserwację kolejki i aktywnych zadań;
- podgląd postępu oraz błędu;
- ponowienie zadania;
- przejście do dokumentów lub rezultatów utworzonych przez job.

API musi stosować zamkniętą listę typów jobów i walidowane parametry. Nie może przyjmować dowolnej komendy shellowej.

## 8. Przenośność środowisk

| Środowisko | Durable storage | Scratch | Worker |
|---|---|---|---|
| Lokalny Compose | volume/katalog lokalny | volume kontenera | kontener |
| NAS | MinIO | volume lub bind mount NAS | kontener na NAS |
| AWS | S3 | ephemeral disk ECS/EKS/EC2 lub EBS | ECS/EKS/EC2 |
| Google Cloud | GCS | ephemeral disk Cloud Run/GKE/VM lub Persistent Disk | Cloud Run Jobs/GKE/VM |

Pipeline nie powinien wiedzieć, gdzie fizycznie znajduje się durable storage. Powinien otrzymać lokalnie zmaterializowane wejście i zwrócić listę artefaktów do zapisania.

## 9. Etapy migracji

### Etap 0 — inwentaryzacja

- znaleźć wszystkie skrypty uruchamiane lokalnie i ich harmonogramy;
- zinwentaryzować katalogi, rozmiary, formaty i retencję;
- sklasyfikować każdy plik jako durable, checkpoint albo scratch;
- wskazać procesy zależne od lokalnych ścieżek i poświadczeń;
- zapisać aktualne czasy wykonania i koszty API/LLM.

### Etap 1 — storage

- ustalić finalny kontrakt `ObjectStorage`;
- zachować lokalny adapter jako fallback;
- ustalić konwencję kluczy;
- dodać natywny adapter GCS dopiero przed realnym wdrożeniem w Google Cloud;
- dodać raport zajętości według prefiksów i klas danych;
- przygotować migrację z dry-run, checksumą i raportem;
- nie usuwać źródeł przed weryfikacją migracji i backupu.

### Etap 2 — ogólna kolejka jobów

- dodać model oraz migrację bazy;
- wyodrębnić worker z procesu Flask;
- zaimplementować claim, heartbeat, retry i recovery;
- dodać limity współbieżności według typu joba;
- dodać podstawowe API oraz testy.

### Etap 3 — pierwszy proces end-to-end

Jako pierwszy przenieść jeden ograniczony proces, prawdopodobnie `dynamodb_sync`:

- wydzielić logikę CLI do funkcji/usługi;
- pozostawić CLI jako cienki wrapper;
- uruchamiać tę samą usługę z workera;
- materializować wejścia i synchronizować rezultaty;
- pokazywać status w WWW;
- sprawdzić restart w połowie wykonania i bezpieczne ponowienie.

### Etap 4 — pozostałe pipeline'y

- YouTube i transkrypcje;
- pobieranie stron oraz konwersja markdown;
- analiza chunków;
- embeddingi;
- naprawy i migracje danych;
- zadania konserwacyjne oraz cleanup.

Każdy proces powinien stać się idempotentny albo mieć jasno opisane zasady ponawiania.

### Etap 5 — scheduler i wyłączenie lokalnych jobów

- dodać harmonogram na NAS;
- monitorować nowe joby równolegle z dotychczasowym procesem przez okres próbny;
- usunąć zależności od lokalnych ścieżek;
- wyłączyć Task Scheduler/cron na komputerach;
- udokumentować procedurę awarii i ręcznego ponowienia.

### Etap 6 — gotowość chmurowa

- test kontraktowy adapterów object storage;
- konfiguracja przez sekrety środowiska;
- brak stałych adresów NAS i ścieżek QNAP w kodzie aplikacji;
- limity CPU, RAM, czasu i równoległości jobów;
- metryki kosztów storage, transferu, LLM i zewnętrznych API;
- backup PostgreSQL oraz polityka retencji object storage.

## 10. Retencja i koszty

Metryki do zbierania:

- bajty i liczba obiektów według prefiksu;
- liczba PUT/GET/HEAD/LIST;
- transfer wejściowy i wyjściowy;
- rozmiar scratch przed i po jobie;
- czas życia checkpointów;
- koszt LLM i API przypisany do joba;
- koszt ponowień.

Proponowana polityka początkowa:

- durable: bez automatycznego usuwania;
- checkpoint: retencja zależna od typu, np. 7–30 dni;
- scratch po sukcesie: natychmiastowe usunięcie;
- scratch po błędzie: 1–7 dni na diagnostykę;
- cache modeli: osobna polityka i limit rozmiaru;
- wersjonowanie object storage: włączyć tylko świadomie, z lifecycle.

Przy małej obecnej objętości koszt pojemności chmurowej będzie niski. Większe ryzyko kosztowe stanowią transfer, duża liczba małych operacji, wersjonowanie, soft delete oraz powtarzanie drogich jobów.

## 11. Niezawodność i bezpieczeństwo

- job zapisuje heartbeat;
- osierocony job wraca do kolejki albo trafia do stanu wymagającego decyzji;
- zapis rezultatu powinien być atomowy z perspektywy stanu joba;
- upload powinien używać tymczasowego klucza lub checksumy, jeśli częściowy wynik jest ryzykiem;
- retry ma backoff i limit prób;
- sekrety MinIO/AWS/GCP pozostają w Vault lub mechanizmie sekretów platformy;
- bucket nie jest publiczny;
- dostęp przeglądarki odbywa się przez API lub krótkotrwałe presigned URLs;
- każdy typ joba ma osobne limity parametrów, czasu i współbieżności;
- należy regularnie testować odtworzenie PostgreSQL i object storage z backupu.

## 12. Otwarte decyzje

Przed implementacją wspólnej kolejki należy zdecydować:

1. Czy końcowy markdown jest durable, czy możliwym do odtworzenia checkpointem?
2. Które artefakty LLM przechowywać i jak długo?
3. Czy scratch na NAS ma być efemerycznym volume, czy widocznym bind mountem ułatwiającym diagnostykę?
4. Jak długo zachowywać scratch nieudanych jobów?
5. Czy jeden worker sekwencyjny wystarczy, czy od początku potrzebne są osobne kolejki CPU/IO/LLM?
6. Czy `document_analysis_jobs` migrować do wspólnej tabeli, czy pozostawić jako kolejkę domenową korzystającą ze wspólnego runtime'u?
7. Czy scheduler ma być częścią workera, osobnym kontenerem, czy ma tylko okresowo tworzyć rekordy w PostgreSQL?
8. Czy użytkownik może anulować każdy job, czy tylko wybrane typy?
9. Jakie dane mają być dostępne przez presigned URLs?
10. Czy wymagane jest działanie podczas niedostępności internetu, a jeśli tak, które joby mają być kolejkowane do późniejszego wykonania?

## 13. Kryteria zakończenia migracji NAS

Migrację można uznać za zakończoną, gdy:

- wszystkie produkcyjne joby wykonują się na NAS;
- można je uruchomić i obserwować z telefonu przez WWW;
- wyłączenie komputera użytkownika nie zatrzymuje żadnego procesu;
- restart API nie przerywa trwale jobów;
- restart workera prowadzi do kontrolowanego wznowienia lub ponowienia;
- trwałe dane znajdują się w PostgreSQL i MinIO;
- scratch można usunąć bez utraty źródła prawdy;
- istnieje zweryfikowany backup oraz procedura odtworzenia;
- nie działają już lokalne harmonogramy;
- wykorzystanie miejsca, retencja i koszty są mierzalne.

## 14. Rekomendacja robocza

Na obecnym etapie rekomendowany wariant do dalszej oceny to:

- PostgreSQL jako trwała kolejka jobów;
- osobny kontener `lenie-worker` na NAS;
- MinIO jako durable storage;
- NAS-local volume jako scratch workera;
- `LocalObjectStorage` dla przenośnego Compose;
- `S3ObjectStorage` dla MinIO i AWS;
- przyszły natywny `GCSObjectStorage` dla Google Cloud;
- migracja po jednym pipeline'ie, zaczynając od procesu o ograniczonym zakresie;
- brak Redis/Celery do czasu, gdy pomiary wykażą taką potrzebę.

Ta rekomendacja nie jest jeszcze decyzją implementacyjną.

## 15. Wieloużytkownikowość

Lenie ma dziś działać dla kilku zaufanych osób (rodzina/znajomi), nie tylko dla jednego użytkownika — to jest realny, wdrażany zakres, opisany osobno w [multi-user-household.md](multi-user-household.md), żeby nie rozdmuchiwać tego dokumentu. W skrócie: baza (`users`/`api_keys`) już istnieje i działa w modelu „wspólna biblioteka, zaufani domownicy” — nie trzeba Redis, Celery ani izolacji per-workspace na tym etapie.

Skalowanie do usługi komercyjnej dla wielu, niezaufanych wobec siebie użytkowników (on-prem, chmura albo hybrydowo) to osobny, czysto edukacyjny eksperyment myślowy — patrz [commercial-multi-tenant-scaling-experiment.md](../commercial-multi-tenant-scaling-experiment.md). Jedyna rzecz stamtąd wartą zrobienia już teraz, bo jest tania: nadanie opcjonalnego właściciela (`initiated_by_user_id`) rekordom jobów, żeby uniknąć kosztownej migracji danych, gdyby taka decyzja kiedyś zapadła — opisane w [multi-user-household.md](multi-user-household.md).

## 16. Dostawcy i implementacje zgodne z S3

Warstwa aplikacyjna nie powinna być związana z MinIO ani AWS. Dostawca ma być wybierany przez konfigurację endpointu, poświadczeń i niewielkiego zestawu opcji zgodności.

Określenie „S3-compatible” zazwyczaj oznacza zgodność podstawowych operacji obiektowych, a nie wszystkich usług i rozszerzeń AWS. Przed wyborem dostawcy trzeba zweryfikować dokładnie funkcje używane przez Lenie.

### 16.1. CloudFerro

CloudFerro oferuje Object Storage z API zgodnym z Amazon S3. Standardowe biblioteki takie jak `boto3`, AWS CLI i narzędzia S3 mogą korzystać z niego po ustawieniu właściwego endpointu.

Z oficjalnych materiałów wynika, że infrastruktura object storage CloudFerro jest oparta o Ceph, nie MinIO. Dla aplikacji nie powinno mieć to znaczenia — oba rozwiązania udostępniają API S3.

Potencjalne zalety:

- europejski dostawca;
- regiony obejmujące Warszawę i Frankfurt;
- możliwość uruchomienia compute i Kubernetes u tego samego dostawcy;
- standardowy oraz cold object storage;
- dane pozostające w UE;
- możliwość użycia tych samych klientów S3 co dla MinIO i AWS.

Elementy wymagające weryfikacji przed wyborem:

- bieżący cennik konkretnego regionu;
- koszty transferu, API i retrieval;
- minimalna retencja cold storage;
- dostępność versioning, Object Lock i presigned URLs;
- limity liczby obiektów oraz wydajność listowania;
- zgodność multipart upload i ETag.

CloudFerro informuje, że bardzo duża liczba obiektów w jednym bucketcie może pogarszać wydajność listowania. Konwencja kluczy i podział na buckety powinny uwzględniać przewidywaną skalę.

### 16.2. QNAP QuObjects

QuObjects to aplikacja uruchamiana bezpośrednio na QNAP NAS, udostępniająca lokalny object storage zgodny z S3. Jest alternatywą dla uruchamiania MinIO w kontenerze.

Deklarowane funkcje obejmują:

- bucket i object API;
- multipart upload;
- CORS;
- versioning;
- Object Lock i immutability;
- polityki dostępu;
- współpracę ze standardowymi klientami S3.

QNAP wymaga QTS 5.0 lub nowszego i rekomenduje co najmniej 8 GB RAM. Model TS-453Be jest urządzeniem x86, więc powinien należeć do obsługiwanej kategorii, ale dostępność QuObjects należy potwierdzić w App Center dla używanej wersji firmware i konfiguracji RAM.

Porównanie z MinIO:

| MinIO w kontenerze | QNAP QuObjects |
|---|---|
| Przenośny między NAS i innymi hostami | Związany z platformą QNAP |
| Konfiguracja kontrolowana przez Compose | Zarządzanie z poziomu QTS |
| Podobne środowisko developerskie i produkcyjne | Mniej własnej infrastruktury kontenerowej |
| Osobny kontener i volume | Natywna integracja z NAS |
| Łatwiejsze odtworzenie poza QNAP | Wbudowane funkcje QNAP, Object Lock i administracja |

Przed ostatecznym wyborem MinIO albo QuObjects należy wykonać ten sam test kontraktowy i prosty benchmark na docelowym NAS. Kod aplikacji powinien obsługiwać oba przez `S3ObjectStorage`.

### 16.3. QNAP myQNAPcloud Object

`myQNAPcloud Object` jest publiczną usługą chmurową QNAP zgodną z S3. Nie należy jej mylić z:

- QuObjects działającym lokalnie na NAS;
- myQNAPcloud Storage przeznaczonym bardziej do plików i backupu NAS;
- aplikacjami QNAP służącymi tylko do synchronizacji z zewnętrznymi chmurami.

Usługa jest oferowana w ramach `myQNAPcloud One`, które łączy przestrzeń klasycznego storage i object storage. QNAP deklaruje brak opłat za ingress i egress oraz rozliczanie przede wszystkim zakupionej pojemności.

Zgodność nie obejmuje wszystkich funkcji AWS. Oficjalna dokumentacja wymienia między innymi brak:

- AWS KMS;
- wielu klas storage;
- `RestoreObject`;
- S3 Select;
- S3 Batch Operations.

Dla Lenie może to być wystarczające, jeśli aplikacja ograniczy się do podstawowych operacji, multipart upload, metadata i presigned URLs. Każdą potrzebną funkcję należy jednak potwierdzić testem.

### 16.4. Inni dostawcy chmurowi

Lista kandydatów do późniejszego porównania:

| Dostawca | Charakterystyka do oceny |
|---|---|
| AWS S3 | Punkt odniesienia dla API, szeroki zestaw funkcji, osobne opłaty za storage, operacje i transfer |
| Backblaze B2 | S3-compatible hot storage, popularny dla backupów i archiwów |
| Cloudflare R2 | S3-compatible, model bez klasycznych opłat za egress, dobre zastosowania internetowe |
| Wasabi | S3-compatible hot storage, prostszy model cenowy, wymagane sprawdzenie retencji i zasad egress |
| OVHcloud | Europejski object storage zgodny z S3, warianty regionalne i wielostrefowe |
| Scaleway | Europejski S3-compatible Object Storage z kilkoma klasami danych |
| DigitalOcean Spaces | Prosty storage S3-compatible z CDN, częściowa zgodność funkcji AWS |
| Hetzner Object Storage | Europejski S3-compatible storage do prostych zastosowań |
| IBM Cloud Object Storage | Rozwiązanie chmurowe i enterprise zgodne z podstawowym API S3 |
| Oracle Cloud Object Storage | Warstwa kompatybilności S3, niepełna zgodność z rozszerzeniami AWS |
| Google Cloud Storage | Preferowany natywny adapter GCS; opcje interoperacyjności nie powinny zastępować testów zgodności |

### 16.5. Inne rozwiązania self-hosted

Poza MinIO i QuObjects istnieją:

- Ceph RGW — dojrzały, rozproszony storage S3, ale znacznie cięższy operacyjnie;
- SeaweedFS — rozproszony storage z bramą S3;
- Garage — lekki rozproszony object storage zgodny z częścią API S3;
- inne bramy S3 dostarczane przez platformy NAS i rozwiązania enterprise.

Dla pojedynczego QNAP nie ma obecnie uzasadnienia dla samodzielnego klastra Ceph. MinIO lub QuObjects są prostsze. Rozwiązania rozproszone należy ponownie ocenić dopiero przy wielu węzłach albo wymaganiu wysokiej dostępności.

### 16.6. Proponowany układ hybrydowy

NAS z RAID nie jest pełnym backupem. Awaria urządzenia, błąd administracyjny, kradzież, pożar lub ransomware mogą objąć wszystkie lokalne kopie.

Możliwy układ:

```text
QuObjects albo MinIO na NAS
            |
            +-- primary storage aplikacji
            |
            `-- replikacja lub backup poza lokalizację
                    |- CloudFerro
                    |- myQNAPcloud Object
                    |- Backblaze B2
                    `- inny dostawca S3-compatible
```

Backup powinien mieć osobne poświadczenia i, jeśli to możliwe, immutability/Object Lock. Konto aplikacji nie powinno mieć prawa usuwania historycznych backupów.

### 16.7. Konfiguracja niezależna od dostawcy

Przykładowa konfiguracja:

```env
STORAGE_DRIVER=s3
STORAGE_ENDPOINT_URL=https://endpoint.example
STORAGE_BUCKET=lenie-storage
STORAGE_ACCESS_KEY=...
STORAGE_SECRET_KEY=...
STORAGE_REGION=...
STORAGE_ADDRESSING_STYLE=path
```

Dodatkowe opcje mogą obejmować:

- wymuszenie path-style albo virtual-hosted-style;
- konfigurację TLS i własnego CA;
- timeouty i retry;
- rozmiar części multipart upload;
- maksymalną współbieżność transferów;
- checksum algorithm;
- server-side encryption;
- prefix przypisany do środowiska lub workspace.

W kodzie nie powinny powstawać gałęzie `if cloudferro`, `if qnap` ani `if wasabi`, o ile dostawca nie wymaga faktycznie odmiennego zachowania. Różnice protokołu należy izolować w adapterze i konfiguracji.

### 16.8. Test kontraktowy S3

Każdy kandydat powinien przejść automatyczny zestaw testów na osobnym bucketcie:

- utworzenie i usunięcie obiektu;
- upload/download małego i dużego pliku;
- streaming bez ładowania całego pliku do RAM;
- multipart upload i przerwanie niedokończonego uploadu;
- `HEAD` i metadata;
- `Content-Type`;
- listowanie z prefiksem i paginacją;
- klucze zawierające spacje oraz Unicode;
- kopiowanie obiektu;
- presigned GET i PUT;
- zachowanie `ETag` oraz checksum;
- retry po błędzie sieciowym;
- versioning i Object Lock, jeśli będą wymagane;
- polityka lifecycle;
- równoległe zapisy oraz idempotencja;
- pomiar czasu i liczby wykonanych requestów.

Testy destrukcyjne muszą działać tylko na bucketcie lub prefiksie przeznaczonym do testów.

### 16.9. Kryteria porównania dostawców

Decyzja nie powinna opierać się wyłącznie na cenie za GB. Należy porównać:

- koszt storage;
- koszt PUT/GET/HEAD/LIST;
- koszt i limit egress;
- koszt retrieval oraz minimalną retencję;
- lokalizację i jurysdykcję danych;
- opóźnienie z miejsca działania workerów;
- trwałość i SLA;
- versioning, lifecycle, Object Lock i encryption;
- presigned URLs;
- limity liczby obiektów, rozmiaru i requestów;
- jakość dokumentacji i wsparcia;
- możliwość eksportu danych i koszt migracji;
- dostępność narzędzi backupu oraz replikacji;
- stopień rzeczywistej zgodności z używanym podzbiorem S3.

### 16.10. Rekomendacja do dalszej analizy

Do krótkiej listy dla instalacji Lenie należy przyjąć:

1. QuObjects jako natywny primary storage na QNAP;
2. MinIO jako przenośny primary storage zarządzany przez Compose;
3. CloudFerro jako europejski wariant chmurowy lub off-site backup;
4. myQNAPcloud Object jako prosty backup zintegrowany z ekosystemem QNAP;
5. Backblaze B2 lub Cloudflare R2 jako alternatywy kosztowe.

Następny krok decyzyjny to uruchomienie QuObjects na NAS, wykonanie testu kontraktowego oraz porównanie go z działającym MinIO pod względem zużycia RAM, przepustowości, obsługi, backupu i odtwarzania.
