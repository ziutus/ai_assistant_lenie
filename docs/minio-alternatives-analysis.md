# Alternatywy dla MinIO — analiza dla Lenie

Data analizy: 2026-09-19.

Status: notatka analityczna. Nie podjęto decyzji o zmianie storage. Testy,
pilotaż i ewentualna migracja pozostają do rozważenia w przyszłości; w ramach
tej analizy nie wykonywano operacji na NAS-ie ani zmian konfiguracji.

## Materiał źródłowy i jego zakres

[Robin Moffatt, „Alternatives to MinIO for single-node local S3”](https://rmoff.net/2026/01/14/alternatives-to-minio-for-single-node-local-s3/)
(14 stycznia 2026) porównuje zamienniki MinIO dla lokalnego demo DuckDB/Iceberg.
Kryteriami są prostota uruchomienia, Docker, zgodność S3 i dostępność rozwiązania.
Autor wyłącza ze swojej oceny zastosowania produkcyjne. Jego testy pomagają
wybrać kandydatów, ale nie potwierdzają trwałości danych, niezawodności backupu
ani wydajności na naszym QNAP.

Dla Lenie to istotny temat: MinIO jest magazynem trwałych danych, a nie tylko
emulatorem S3 do demonstracji. Źródła dokumentów, uploady i ilustracje muszą
przetrwać restart i dać się odtworzyć wraz z PostgreSQL.

## Aktualizacja względem artykułu

W dniu analizy [repozytorium MinIO](https://github.com/minio/minio) było
zarchiwizowane (od 25 kwietnia 2026) i oznaczone jako nieutrzymywane.
To argument za rozważeniem następcy, bez automatycznego wniosku o konieczności
natychmiastowego przełączenia działającej instalacji.

Nasz [Compose NAS](../infra/docker/compose.nas.yaml) przypina obraz odpowiadający
`RELEASE.2025-09-07T16-13-09Z`, przechowywany w prywatnym registry. Zapewnia to
powtarzalność wdrożenia, ale nie rozwiązuje problemu dalszego utrzymania upstream.
Informacje o wdrożeniu wynikają z repozytorium; nie sprawdzano bieżącego stanu NAS-a.

Styczniowe oceny wersji alternatyw również nie powinny być traktowane jako
aktualny ranking. Przykładowo [quickstart Garage](https://garagehq.deuxfleurs.fr/documentation/quick-start/)
opisuje od wersji 2.3.0 automatyzację inicjalizacji przez `--single-node`
i `--default-bucket`, co osłabia zarzut skomplikowanej konfiguracji z artykułu.

## Dopasowanie do architektury Lenie

[Mapa wdrożeń](deployment/README.md) wskazuje NAS jako rzeczywiste środowisko
projektu. [Dokumentacja storage](storage.md) rozdziela trwałe obiekty od
tymczasowych plików roboczych konwerterów.

[ObjectStorage](../backend/library/storage.py) ma implementacje `LocalStorage`
i `S3Storage`. Obecna implementacja S3 korzysta z:

- `PutObject`, `GetObject` i `HeadObject`;
- `ListObjectsV2` z paginacją;
- `Content-Type` przy zapisie;
- podpisanych URL-i GET do pobierania obrazów przez przeglądarkę.

Nie ma potrzeby projektowania osobnego adaptera dla każdego serwera zgodnego
z S3. Punktem wyjścia dla alternatywy jest `STORAGE_BACKEND=s3`, endpoint,
region i poświadczenia. Zgodność konkretnego serwera wymaga jednak potwierdzenia.

Ważne zależności poza samym API:

- Osobny `STORAGE_PUBLIC_ENDPOINT_URL` służy do podpisywania adresów dostępnych
  z przeglądarki; wewnętrzny adres kontenera nie wystarczy.
- Compose wiąże backend i workery z healthcheckiem MinIO. Inicjalizacja bucketa,
  healthcheck, wolumeny oraz konfiguracja Vault wymagają uwzględnienia przy zmianie.
- `LocalStorage` nie generuje podpisanych URL-i, więc powrót do zwykłego katalogu
  nie zachowuje wszystkich obecnych zachowań interfejsu.
- Adapter odczytuje i zapisuje pełne bufory `bytes`; domyślny limit uploadu to
  250 MiB. Zmiana serwera nie usuwa kosztu pamięci po stronie aplikacji.

## Ocena kandydatów

Poniższa kolejność jest oceną dopasowania do Lenie, a nie wynikiem benchmarku.

| Rozwiązanie | Ocena dla naszego projektu |
|---|---|
| **SeaweedFS** | Pierwszy kandydat do ewentualnego przyszłego pilotażu. Aktualny quickstart oferuje `weed mini`, pojedynczy proces i konfigurację kluczy oraz bucketa przez zmienne. Pasuje do wdrożenia kontenerowego; zużycie zasobów i odtwarzanie wymagają oceny. |
| **Garage** | Drugi kandydat. Nie należy odrzucać go tylko na podstawie konfiguracji opisanej w styczniowym artykule. Trzeba uwzględnić ograniczenia API oraz trwałość danych i metadanych. |
| **QNAP QuObjects** | Opcja już uwzględniona w naszym planie storage. Wymaga potwierdzenia dostępności na konkretnym urządzeniu i zgodności z Lenie. Rozwiązanie kontenerowe preferujemy ze względu na łatwiejsze odtworzenie poza QNAP. |
| **S3Proxy, RustFS, Zenko CloudServer** | Poza pierwszą turą porównania: analiza nie wykazała konkretnej przewagi dla Lenie nad pierwszymi kandydatami. Nie oznacza to ich dyskwalifikacji ani potwierdzenia aktualności styczniowych ocen dojrzałości. |
| **Ceph / Apache Ozone** | Brak uzasadnienia dla wprowadzania takiej infrastruktury przy pojedynczym domowym NAS-ie i obecnym zakresie potrzeb. |

[Dokumentacja SeaweedFS](https://github.com/seaweedfs/seaweedfs#quick-start)
opisuje `weed mini` jako wariant dla pojedynczego węzła, także dla zastosowań
produkcyjnych. Jednocześnie uruchamia on kilka komponentów wewnętrznych;
pojedynczy proces nie jest dowodem niskiego zużycia zasobów na QNAP.

[Dokumentacja Garage](https://garagehq.deuxfleurs.fr/documentation/quick-start/)
zastrzega brak redundancji w przykładzie jednowęzłowym oraz ograniczenia API,
m.in. ACL i policies. Przykładowe ścieżki tymczasowe nie są konfiguracją
trwałego magazynu. Niezależnie od wyboru, pojedynczy NAS nie zastępuje backupu.

## Co warto sprawdzić w przyszłości

Poniższa lista określa kryteria przyszłej oceny, nie zadania uruchomione w ramach
tej notatki:

1. Zapis i odczyt rzeczywistych PDF/HTML/obrazów przez klienta Lenie, brakujący
   klucz, nadpisanie, zachowanie `Content-Type` i listowanie ponad 1000 obiektów.
2. Podpisane URL-e pobierane przez przeglądarkę, także przez VPN; poprawny odczyt
   z workera nie potwierdza tego scenariusza.
3. Restart oraz odtworzenie backupu do pustego środowiska z kontrolą zawartości.
4. RAM, CPU i obciążenie dysków przy imporcie i czytaniu. Limit obecnego kontenera
   MinIO to 768 MiB RAM i 0,5 CPU — to limit konfiguracji, nie pomiar zużycia.
5. Większe pliki i wpływ buforowania w aplikacji.

[Testy jednostkowe storage](../backend/tests/unit/test_storage.py) korzystają
z mocków klienta S3. Weryfikują zachowanie adaptera, ale nie dowodzą zgodności
alternatywnego serwera. W tej analizie nie uruchamiano testów integracyjnych.

Jeśli w przyszłości zapadnie decyzja o migracji, należy kopiować obiekty przez
API S3 do osobnego magazynu, zachowując klucze i metadane, z kontrolą sum treści.
Nie należy traktować podpięcia dotychczasowego wolumenu MinIO do innego serwera
jako migracji. Przełączenie wymaga uwzględnienia zapisów powstałych podczas
kopiowania, końcowej synchronizacji oraz zasad wycofania zmiany.

[storage_migrate.py](../backend/imports/storage_migrate.py) kopiuje lokalny
katalog do storage; nie jest gotowym narzędziem migracji S3 → S3.

## Wniosek

Zachować obecną architekturę `ObjectStorage` i konfigurację wdrożenia.
SeaweedFS oraz Garage stanowią sensowną listę kandydatów do przyszłej oceny.
Zakończenie utrzymania MinIO uzasadnia powrót do tematu, ale artykuł i przegląd
kodu nie wystarczają do zatwierdzenia konkretnego następcy.

Notatka uzupełnia [plan storage i jobów](deployment/nas/storage-and-jobs-migration-plan.md),
w szczególności jego sekcje o QuObjects i innych rozwiązaniach self-hosted.
Nie zmienia tego planu w decyzję o migracji.
