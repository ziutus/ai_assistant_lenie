# Eksperyment myślowy: AWS / Google Cloud

Status: eksperyment myślowy, niski priorytet — nauka architektury w wolnym czasie, horyzont 1+ rok  
Powiązane: [../README.md](../README.md) · [../commercial-multi-tenant-scaling-experiment.md](../commercial-multi-tenant-scaling-experiment.md) · [../nas/storage-and-jobs-migration-plan.md](../nas/storage-and-jobs-migration-plan.md)

## Uwaga: to nie jest to samo co `docs/aws-roadmap.md`

Repozytorium ma już `docs/aws-roadmap.md`, ale opisuje on **inną, wcześniejszą architekturę** — serwerlessową (Lambda + API Gateway + DynamoDB + SQS), sprzed przejścia na NAS jako główne środowisko. Ten dokument pyta o coś innego: co by było, gdyby **dzisiejszy** kształt aplikacji (Docker Compose: Flask API + PostgreSQL + MinIO + workery) uruchomić na AWS albo GCloud zamiast na NAS-ie. To dwa różne pytania architektoniczne, nie kontynuacja tego samego planu.

## Kiedy to w ogóle ma sens rozważać

Dopiero po spełnieniu kryteriów „gotowości chmurowej” z głównego planu NAS (Etap 6: konfiguracja przez sekrety, brak zahardkodowanych ścieżek QNAP, test kontraktowy adapterów storage) — patrz [../nas/storage-and-jobs-migration-plan.md](../nas/storage-and-jobs-migration-plan.md).

## Co NIE robić teraz

Nie budować kodu pod konkretnego hiperskalera na zapas. `backend/library/storage.py` już dziś obsługuje AWS S3 tym samym kodem co MinIO (`STORAGE_BACKEND=s3`) — to jedyna „inwestycja w przyszłość”, jaka ma sens przed realną decyzją o migracji.
