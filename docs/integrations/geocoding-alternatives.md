# Geokodowanie i NER miejsc: alternatywy odłożone

Działa spaCy `pl_core_news_lg` (NER) + LocationIQ (weryfikacja istnienia miejsca) +
LLM (istotność), czyli [ADR-018](../adr/adr-018-geo-place-ner-locationiq.md).
Implementacja: [ner-integration-plan.md](../ner-integration-plan.md) (etap 3).
Ten plik trzyma to, co ADR-018 odłożył: opcje na dzień, w którym darmowy tier
LocationIQ (5 000 zapytań/dzień) albo jakość spaCy przestaną wystarczać.

## Hostowane API geokodujące (stan na 2026-07-09, ceny do odświeżenia przed użyciem)

| Usługa | Oparta na OSM/Nominatim? | Darmowy limit | Uwagi |
|---|---|---|---|
| [Publiczny Nominatim OSM](https://operations.osmfoundation.org/policies/nominatim/) | Tak (oficjalny) | 1 zap./s | Wymagany User-Agent/Referer, masowe skrypty max 4 zap./min, obowiązkowy cache. **Zabronione użycie komercyjne**; aplikacje oparte na geokodowaniu „muszą uruchomić własną usługę" |
| [LocationIQ](https://locationiq.com/pricing) | Tak, API-kompatybilne z Nominatim | 5 000 zap./dzień, 2 zap./s | Płatnie od ~$45-50/mies. (~10k/dzień). Użycie komercyjne dozwolone z atrybucją. **Wybrane w ADR-018** |
| [Geoapify](https://www.geoapify.com/openstreetmap-geocoding/) | Częściowo (OSM + GeoNames + OpenAddresses) | 3 000 kredytów/dzień | Hojny darmowy tier, w tym geokodowanie wsadowe |
| [OpenCage](https://opencagedata.com/pricing) | Częściowo (agreguje kilka źródeł) | 2 500 zap./dzień | Darmowy limit to trial do testów, nie tier produkcyjny |
| [Photon (komoot)](https://github.com/komoot/photon) | Tak (inny silnik, dane OSM) | publiczna instancja ~1 zap./s, intensywne użycie banowane | Brak płatnego API; sensowny głównie jako self-host |

## Self-hosting: Photon zamiast Nominatim

| | Nominatim | Photon |
|---|---|---|
| Dysk (pełna planeta) | ~800 GB+ | ~95 GB |
| RAM (import) | 64-128 GB | 64 GB |
| Dysk (wycinek regionalny) | ~10-50 GB | proporcjonalnie mniej |
| Silnik | PostgreSQL + PostGIS | Elasticsearch/Lucene |

Do pytania „czy ta nazwa istnieje w OSM" Photon wystarcza i jest wielokrotnie
lżejszy, więc to pierwszy kandydat na self-hosting. Przy odmienionych nazwach
(„w Cieśninie Ormuz") pomocne jest `pg_trgm` (fuzzy match na trigramach).

## Upgrade NER: HerBERT (Allegro) zamiast spaCy

Wyższa surowa dokładność niż `pl_core_news_lg`, ale transformer:

- CPU: kilka do kilkunastu sekund na fragment (wariant `base`), `large` wolniej.
  Obecny NAS (Celeron, bez GPU) się nie nadaje.
- GPU: NVIDIA 6-12 GB VRAM wystarcza (RTX 3060/4060, nawet GTX 1660 6 GB);
  karta konsumencka, nie serwerowa. AMD/ROCm gorzej wspierane przez PyTorch.
- RAM 16 GB+, dysk ~2 GB na PyTorch + wagi (setki MB do ~1,5 GB).
- Zależności: `transformers`, `torch`; nazwę modelu NER dla HerBERT trzeba
  zweryfikować na HuggingFace w momencie wdrożenia.

Wracać do tego dopiero, gdy jakość spaCy okaże się niewystarczająca w praktyce.
