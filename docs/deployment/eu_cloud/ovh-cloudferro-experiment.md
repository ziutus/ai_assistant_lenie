# Eksperyment myślowy: OVH / CloudFerro (chmura europejska)

Status: eksperyment myślowy, niski priorytet — nauka architektury w wolnym czasie, horyzont 1+ rok  
Powiązane: [../README.md](../README.md) · [../commercial-multi-tenant-scaling-experiment.md](../commercial-multi-tenant-scaling-experiment.md) · [../hyperscalers/aws-gcloud-experiment.md](../hyperscalers/aws-gcloud-experiment.md)

## Storage: już opisane, nie duplikować

Porównanie dostawców object storage zgodnych z S3 (CloudFerro, QNAP QuObjects, myQNAPcloud Object, Backblaze B2, Wasabi i inni) jest już szczegółowo opisane w głównym planie NAS: [`../nas/storage-and-jobs-migration-plan.md`, sekcja 16](../nas/storage-and-jobs-migration-plan.md#16-dostawcy-i-implementacje-zgodne-z-s3). To zostaje tam, bo dotyczy realnej, bliskiej potrzeby (backup off-site z NAS-a), nie tylko tego eksperymentu.

Ten dokument dotyczy czegoś szerszego: uruchomienia **całej aplikacji** (nie tylko storage) w chmurze europejskiej.

## Pytanie użytkownika: hiperskaler vs chmura europejska — realna różnica praktyczna

To jest właściwe pytanie do zbadania, gdy temat stanie się aktualny, nie coś, co da się dziś rzetelnie rozstrzygnąć bez researchu.

Warstwa aplikacyjna Lenie (patrz `backend/library/storage.py`) jest już zaprojektowana tak, żeby ta decyzja była odwracalna na poziomie storage — `S3ObjectStorage` obsługuje MinIO, AWS i dowolnego dostawcę S3-compatible tym samym kodem. Compute i baza danych nie mają dziś takiej abstrakcji i nie muszą jej mieć, dopóki nie pojawi się realna potrzeba wyjścia poza jeden Docker Compose.
