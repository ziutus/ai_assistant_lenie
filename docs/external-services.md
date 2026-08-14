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
| MinIO / S3 | Magazyn obiektów | `library/storage.py` | Kontenerowe healthchecki, poza panelem |

Serwisy lokalne (PostgreSQL, NER, Vault) nie są usługami zewnętrznymi. NER ma
już własne `/healthz`; statusy kontenerów pozostają w Docker Compose.
