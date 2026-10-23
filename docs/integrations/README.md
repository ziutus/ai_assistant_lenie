# Integracje Lenie AI

Przegląd integracji, które Lenie ma i które może mieć. Ten katalog opisuje
**kierunek i decyzje** (po co integracja, kiedy ma sens, czego wymaga).
Techniczny spis usług sieciowych, które działają dziś, wraz z obserwacją statusu
jest w [external-services.md](../external-services.md); nie powtarzamy go tutaj.

## Kierunki integracji

| Kierunek | Przykłady | Gdzie opisane |
|---|---|---|
| **Z zewnątrz do Lenie** (zbieranie) | wtyczka Chrome, RSS/feedy, Gmail, YouTube, PDF, LinkedIn/Facebook | [web_chrome_extension/CLAUDE.md](../../web_chrome_extension/CLAUDE.md), [feed-and-feed-review-flow.md](../feed-and-feed-review-flow.md), `backend/imports/CLAUDE.md` |
| **Z Lenie na zewnątrz** (zapis) | notatki Obsidian (`/lenie-obsidian-note`), kontakty Google | [ADR-028](../adr/adr-028-google-contacts-api-sync.md) |
| **Wzbogacanie danych** (usługi pytane na żądanie) | LocationIQ, Wikidata, Overpass, CEIDG, adresy.app, GitHub, Fabryka AI | [external-services.md](../external-services.md) |
| **Modele i przetwarzanie** | CloudFerro (Bielik, embeddingi), OpenAI, ARK Labs, AssemblyAI | [ADR-013](../adr/adr-013-custom-llm-abstraction.md), [ADR-011](../adr/adr-011-assemblyai-sole-transcription.md) |
| **Infrastruktura** | MinIO/S3, Vault, relay VPN w Google Cloud | [storage.md](../storage.md), [ADR-023](../adr/adr-023-gcloud-vpn-relay-nas-access.md) |

## Integracje działające

Szczegóły klienta, klucza i obserwacji statusu: [external-services.md](../external-services.md).

- **Wiedza i geografia**: LocationIQ ([ADR-018](../adr/adr-018-geo-place-ner-locationiq.md)),
  Wikidata, Overpass/OpenStreetMap.
- **Dane o firmach i adresach**: CEIDG (`ceidg_client.py`, `CEIDG_API_KEY`),
  adresy.app (`address_validation_client.py`, `ADRESY_APP_API_KEY`).
- **Repozytoria**: publiczne statystyki GitHub (`github_repo_stats.py`, bez klucza).
- **Decyzje typowane**: Fabryka AI (`fabryka_client.py`, `FABRYKA_API_KEY`).
- **Obsidian** (w obie strony): [obsidian-sync-folders.md](../deployment/nas/obsidian-sync-folders.md).

## Integracje rozważone i odłożone

| Usługa | Wniosek | Notatka |
|---|---|---|
| Shodan | Bez stałego publicznego IP nie ma sensu; do wznowienia po jego uzyskaniu | [shodan.md](shodan.md) |

## Zasady dla nowych integracji

1. **Klucze tylko w Vault**, odczyt przez `config_loader` (wzorzec: `ceidg_client.py`).
   Brak klucza oznacza wyłączenie funkcji z ostrzeżeniem w logu, nie błąd aplikacji.
2. **Ruch wychodzący przez `safe_http.py`**, gdy adres pochodzi z danych użytkownika.
3. **Cache w bazie z datą pobrania i TTL**, gdy usługa jest płatna lub ma limity.
   Zewnętrzne API nie jest odpytywane przy każdym otwarciu dokumentu.
4. **Obserwacja statusu**: wywołania zapisujemy do `external_service_events`
   (albo `llm_usage_logs` dla modeli), żeby `/service-status` pokazywał stan rzeczywisty.
5. **Dane o osobach prywatnych**: wzbogacamy firmy i domeny, nie prywatne adresy
   osób. Wynik jest faktem ze źródłem, jak w panelu „Fakty i źródła” kontaktu.
6. **Zadania cykliczne** idą przez kolejkę jobów i workera, nie przez lokalny cron
   (zob. [storage-and-jobs-migration-plan.md](../deployment/nas/storage-and-jobs-migration-plan.md)).
7. Każda nowa integracja dostaje wiersz w [external-services.md](../external-services.md)
   po uruchomieniu, a decyzja o rezygnacji lub odłożeniu trafia do tabeli powyżej.
