# Usługi zewnętrzne

Referencyjny spis integracji sieciowych używanych przez Lenie. Status ekranu
`/service-status` opiera się na wynikach rzeczywistych wywołań, nie na
syntetycznych ani płatnych probe'ach.

| Usługa | Zastosowanie | Klient / konfiguracja | Obserwacja statusu |
|---|---|---|---|
| CloudFerro Sherlock | LLM Bielik i embeddingi BGE/E5 | `library/ai.py`, `library/embedding.py`; `CLOUDFERRO_SHERLOCK_KEY` | Tak, `llm_usage_logs` |
| Webshare | Rotujące proxy oraz autoryzacja adresu IP | `library/webshare_ip_auth.py`; `WEBSHARE_API_KEY` | Tak, `external_service_events` |
| LocationIQ | Weryfikacja nazw miejsc | `library/locationiq_client.py`; `LOCATIONIQ_API_KEY` | Tak, `external_service_events` |
| Wikidata | Rozróżnianie osób | `library/wikidata_client.py` | Tak, `external_service_events` |
| Overpass / OpenStreetMap | Geometrie infrastruktury | `library/overpass_client.py` | Tak, `external_service_events` |
| ARK Labs | Alternatywny dostawca LLM | `library/api/arklabs/`; konfiguracja ARK Labs | Tak, `llm_usage_logs` (LLM) |
| OpenAI | Opcjonalny dostawca LLM i embeddingów | `library/api/openai/`; `OPENAI_API_KEY` | Tak, `llm_usage_logs` (LLM) |
| AWS Bedrock / Vertex AI | Opcjonalni dostawcy modeli | adaptery `library/api/aws/`, `library/api/google/` | Tak, `llm_usage_logs` (LLM) |
| AssemblyAI | Transkrypcja mowy (STT) dla filmów bez napisów | `library/transcript.py` → `library/api/asemblyai/asemblyai_transcript.py`; `ASSEMBLYAI` | Tak, `transcription_usage` (`GET /transcription_usage`) |
| Firecrawl | Pobranie strony (v2 scrape) przy wzbogacaniu wydarzeń świata, tylko jawny krok `web` | `library/web_search_client.py`; `FIRECRAWL_API_KEY` | Saldo kredytów z API dostawcy (`GET /provider_balances`), sekcja „Salda i limity płatnych usług" na `/service-status`; wywołania nie trafiają do rejestru zdarzeń |
| Serper | Wyszukiwarka Google (wzbogacanie wydarzeń, krok `web`) | `library/web_search_client.py`; `SERPER_DEV_APIKEY` | Jak Firecrawl: pozostałe kredyty z API (Serper nie podaje planu, więc bez ostrzeżenia „mało") |
| YouTube napisy (przez proxy Webshare lub bezpośrednio) | Pobieranie napisów w `feed_daily` i `/website_youtube_retry_captions` | `library/youtube_processing.py`; `WEBSHARE_API_KEY` | Tak, `external_service_events` (`youtube_captions`, operacje `via_webshare_proxy` / `direct`; blokada Google = `GoogleSorryBlock`) — karty na `/service-status`, okno do 30 dni |
| YouTube (pytubefix) | Metadane i pobieranie filmów | `library/stalker_youtube_file.py`, `library/youtube_processing.py` | Nie — brak dedykowanego rejestru wywołań |
| Google OAuth | Autoryzacja dostępów do Google (np. Gmail) | `library/google_auth.py` | Nie — brak dedykowanego rejestru wywołań |
| AWS Comprehend | Wykrywanie języka tekstu | `library/api/aws/text_detect_language_aws.py` | Nie — brak dedykowanego rejestru wywołań |
| MinIO / S3 | Magazyn obiektów | `library/storage.py` | Kontenerowe healthchecki, poza panelem |

Limity i salda płatnych usług: koszty modeli LLM są na `/llm-costs`, a stan kredytów
usług, które je raportują (Firecrawl, Serper, OpenRouter) lub mają szacunek wpisany
ręcznie (CloudFerro), na `/service-status`. Wszystko przez `GET /provider_balances`.
Pozostałe płatne usługi (AssemblyAI, Webshare, LocationIQ) nie mają jeszcze limitu
w tym widoku; `GET /transcription_usage` pokazuje tylko zużycie AssemblyAI.

Kierunki integracji, zasady dla nowych usług i integracje odłożone:
[integrations/README.md](integrations/README.md).

Serwisy lokalne (PostgreSQL, NER, Vault) nie są usługami zewnętrznymi. NER ma
już własne `/healthz`; statusy kontenerów pozostają w Docker Compose.
