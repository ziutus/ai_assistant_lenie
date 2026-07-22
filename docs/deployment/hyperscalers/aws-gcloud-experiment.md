# Eksperyment myślowy: AWS / Google Cloud

Status: eksperyment myślowy, niski priorytet — nauka architektury w wolnym czasie, horyzont 1+ rok  
Powiązane: [../README.md](../README.md) · [../commercial-multi-tenant-scaling-experiment.md](../commercial-multi-tenant-scaling-experiment.md) · [../nas/storage-and-jobs-migration-plan.md](../nas/storage-and-jobs-migration-plan.md)

## Uwaga: to nie jest to samo co `docs/aws-roadmap.md`

Repozytorium ma już `docs/aws-roadmap.md`, ale opisuje on **inną, wcześniejszą architekturę** — serwerlessową (Lambda + API Gateway + DynamoDB + SQS), sprzed przejścia na NAS jako główne środowisko. Ten dokument pyta o coś innego: co by było, gdyby **dzisiejszy** kształt aplikacji (Docker Compose: Flask API + PostgreSQL + MinIO + workery) uruchomić na AWS albo GCloud zamiast na NAS-ie. To dwa różne pytania architektoniczne, nie kontynuacja tego samego planu.

## Kiedy to w ogóle ma sens rozważać

Dopiero po spełnieniu kryteriów „gotowości chmurowej” z głównego planu NAS (Etap 6: konfiguracja przez sekrety, brak zahardkodowanych ścieżek QNAP, test kontraktowy adapterów storage) — patrz [../nas/storage-and-jobs-migration-plan.md](../nas/storage-and-jobs-migration-plan.md).

## Co porównać, gdy przyjdzie czas (szkielet, nie research)

| Warstwa | Dzisiaj na NAS | AWS | Google Cloud |
|---|---|---|---|
| Compute (API + worker) | Docker Compose | ECS/EKS/EC2 | Cloud Run / GKE / Compute Engine |
| Baza danych | PostgreSQL w kontenerze | RDS/Aurora PostgreSQL | Cloud SQL for PostgreSQL |
| Object storage | MinIO | S3 (natywnie obsługiwane już dziś przez `S3Storage`) | GCS (wymaga natywnego adaptera albo endpointu interoperacyjności S3, patrz `docs/storage.md`) |
| Sekrety | Vault na NAS | Secrets Manager / SSM Parameter Store | Secret Manager |
| Sieć/egress | Brak kosztu transferu | Płatny egress, NAT Gateway | Płatny egress |
| IaC | Docker Compose | CloudFormation (już częściowo istnieje, patrz `docs/aws-roadmap.md`) i/lub CDK (patrz ADR-016) | brak dziś w repo |
| Tożsamość/dostęp | `api_keys` + Vault | IAM | Cloud IAM |

## Pytania, na które warto znać odpowiedź, zanim się zdecyduje

- Ile realnie kosztowałby transfer i storage przy obecnym wolumenie danych (dziś nieduży — patrz sekcja 10 głównego planu NAS o retencji i kosztach)?
- Czy zależy mi na zarządzanej bazie (mniej operacyjnej roboty) czy na pełnej kontroli (jak dziś na NAS)?
- Czy chcę być w jednym ekosystemie (AWS ma już częściowe IaC w repo) czy uczyć się drugiego od zera (GCloud — czystsza karta, ale podwójny koszt nauki)?
- Czy hiperskaler daje coś, czego nie da europejska chmura (patrz [../eu_cloud/](../eu_cloud/)) — szerszy katalog usług zarządzanych, dojrzalsze SDK, więcej dokumentacji/community — kosztem wyższej ceny i mniejszej kontroli nad lokalizacją danych?

## Co NIE robić teraz

Nie budować kodu pod konkretnego hiperskalera na zapas. `backend/library/storage.py` już dziś obsługuje AWS S3 tym samym kodem co MinIO (`STORAGE_BACKEND=s3`) — to jedyna „inwestycja w przyszłość”, jaka ma sens przed realną decyzją o migracji.
