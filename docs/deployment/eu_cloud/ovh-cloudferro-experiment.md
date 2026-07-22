# Eksperyment myślowy: OVH / CloudFerro (chmura europejska)

Status: eksperyment myślowy, niski priorytet — nauka architektury w wolnym czasie, horyzont 1+ rok  
Powiązane: [../README.md](../README.md) · [../commercial-multi-tenant-scaling-experiment.md](../commercial-multi-tenant-scaling-experiment.md) · [../hyperscalers/aws-gcloud-experiment.md](../hyperscalers/aws-gcloud-experiment.md)

## Storage: już opisane, nie duplikować

Porównanie dostawców object storage zgodnych z S3 (CloudFerro, QNAP QuObjects, myQNAPcloud Object, Backblaze B2, Wasabi i inni) jest już szczegółowo opisane w głównym planie NAS: [`../nas/storage-and-jobs-migration-plan.md`, sekcja 16](../nas/storage-and-jobs-migration-plan.md#16-dostawcy-i-implementacje-zgodne-z-s3). To zostaje tam, bo dotyczy realnej, bliskiej potrzeby (backup off-site z NAS-a), nie tylko tego eksperymentu.

Ten dokument dotyczy czegoś szerszego: uruchomienia **całej aplikacji** (nie tylko storage) w chmurze europejskiej.

## OVH — do rozwinięcia, gdy przyjdzie czas

Dzisiejszy stan wiedzy jest płytki (celowo — priorytet niski). Do zweryfikowania, gdy temat stanie się aktualny:

- OVHcloud Public Cloud (compute, zgodność z OpenStack) jako odpowiednik EC2/Compute Engine;
- OVHcloud Managed PostgreSQL jako odpowiednik RDS/Cloud SQL;
- OVHcloud Object Storage (S3-compatible) — już wymieniony w tabeli dostawców w głównym planie;
- OVHcloud Managed Kubernetes;
- lokalizacje: Francja, Polska (Warszawa), Niemcy — istotne dla rezydencji danych w UE;
- model cenowy — czy rzeczywiście brak zaskakujących opłat za egress, tak jak deklaruje CloudFerro.

## Pytanie użytkownika: hiperskaler vs chmura europejska — realna różnica praktyczna

To jest właściwe pytanie do zbadania, gdy temat stanie się aktualny, nie coś, co da się dziś rzetelnie rozstrzygnąć bez researchu. Szkielet porównania:

| Wymiar | Hiperskaler (AWS/GCloud) | Chmura europejska (OVH/CloudFerro) |
|---|---|---|
| Szerokość katalogu usług zarządzanych | Bardzo szeroka (setki usług) | Węższa — głównie compute, storage, baza, Kubernetes |
| Dojrzałość SDK/dokumentacji/community | Bardzo wysoka | Niższa, ale S3-compatible API pozwala używać tych samych narzędzi (boto3, AWS CLI) |
| Rezydencja danych / RODO | Regiony UE dostępne, ale firma spoza UE (CLOUD Act) | Firma i dane fizycznie w UE — silniejsza gwarancja |
| Przewidywalność cen | Częste opłaty za egress, transfer między usługami | Deklarowany prostszy model, mniej „ukrytych” opłat (do zweryfikowania per dostawca) |
| Vendor lock-in | Wysoki przy usługach natywnych (Lambda, DynamoDB) | Niższy, jeśli trzymać się warstwy S3-compatible + standardowy PostgreSQL/Kubernetes |
| Wsparcie i społeczność | Ogromna (Stack Overflow, fora, kursy) | Mniejsza, ale rosnąca; wsparcie często lepiej dopasowane do klienta europejskiego |

Warstwa aplikacyjna Lenie (patrz `backend/library/storage.py`) jest już zaprojektowana tak, żeby ta decyzja była odwracalna na poziomie storage — `S3ObjectStorage` obsługuje MinIO, AWS i dowolnego dostawcę S3-compatible tym samym kodem. Compute i baza danych nie mają dziś takiej abstrakcji i nie muszą jej mieć, dopóki nie pojawi się realna potrzeba wyjścia poza jeden Docker Compose.
