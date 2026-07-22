# Dokumentacja wdrożeniowa — mapa katalogów

Ten katalog grupuje dokumenty planistyczne według **etapu/środowiska wdrożenia**, nie według tematu. Podział istnieje po to, żeby nie mylić tego, co jest realnie wdrażane, z tym, co jest nauką architektury w wolnym czasie.

## Co jest realne

- **[`nas/`](nas/)** — jedyny katalog opisujący coś, co faktycznie działa albo jest aktywnie wdrażane: własny QNAP NAS, dla mnie i kilku zaufanych domowników/znajomych.
  - [`storage-and-jobs-migration-plan.md`](nas/storage-and-jobs-migration-plan.md) — centralizacja storage (MinIO/S3-compatible) i jobów.
  - [`multi-user-household.md`](nas/multi-user-household.md) — kilku zaufanych użytkowników, bez planowania wydajności pod skalę.

## Co jest eksperymentem myślowym (nauka w wolnym czasie, niski priorytet)

Wszystko poniżej istnieje po jednym powodzie: **żeby decyzje podejmowane dziś w `nas/` nie zamykały tanio dostępnych dróg na przyszłość**, bez budowania tych dróg na zapas. To jest też świadomy poligon do nauki projektowania aplikacji — stąd te dokumenty są utrzymywane, mimo że nic z nich nie jest dziś wdrażane.

- **[`commercial-multi-tenant-scaling-experiment.md`](commercial-multi-tenant-scaling-experiment.md)** — co by się zmieniło, gdyby Lenie miało obsługiwać wielu **niezaufanych** użytkowników (SaaS). Przekrojowy — dotyczy każdego środowiska poniżej.
- **[`federation-experiment.md`](federation-experiment.md)** — bardzo wczesne pytanie: wymiana danych między osobnymi instancjami Lenie AI (inna oś niż liczba użytkowników w jednej instancji).
- **[`hyperscalers/`](hyperscalers/)** — AWS / Google Cloud.
- **[`eu_cloud/`](eu_cloud/)** — OVH / CloudFerro i inni europejscy dostawcy.
- **[`onprem/`](onprem/)** — komercyjne wdrożenie on-premise u kogoś innego (nie to samo co własny domowy NAS).

## Zasada projektowa

Przy podejmowaniu decyzji w `nas/` warto zadać sobie pytanie z dokumentów eksperymentalnych, ale **nie warto** implementować ich odpowiedzi na zapas. Przykład, który już działa dobrze: `backend/library/storage.py` ma jeden interfejs `ObjectStorage` z dwiema implementacjami (`LocalStorage`, `S3Storage`) — S3-compatible pokrywa MinIO, AWS S3 i CloudFerro tym samym kodem, bez gałęzi `if aws`/`if cloudferro`. To jest właściwy poziom przygotowania: tania opcjonalność, zero przedwczesnej złożoności.

Analogiczne tanie decyzje do pilnowania już dziś:
- właściciel/inicjator rekordu (`user_id` na jobach i logach LLM) — patrz [`nas/multi-user-household.md`](nas/multi-user-household.md#3-czego-brakuje-i-warto-dodać-teraz-tanie-bez-kolejek-redis);
- konfiguracja przez zmienne środowiskowe/Vault, nie przez zahardkodowane ścieżki NAS-a — patrz [`nas/storage-and-jobs-migration-plan.md`](nas/storage-and-jobs-migration-plan.md), Etap 6.

Wszystko poza tym — Redis, Celery, PgBouncer, orkiestracja, izolacja workspace, konkretny wybór hiperskalera vs chmury europejskiej — czeka na realną potrzebę.
