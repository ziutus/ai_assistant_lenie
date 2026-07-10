# Rozpoznawanie miejsc geograficznych w tekstach (NER) — plan na przyszłość

> Plan techniczny: problem tagowania miejsc geograficznych (cieśniny, morza, regiony,
> pasma górskie, miasta) wykraczających poza obecny, zamknięty gazetteer krajów
> ([`country_gazetteer.py`](../backend/library/country_gazetteer.py)), proponowany
> pipeline NER → weryfikacja (Nominatim/OSM) → LLM, wraz z wymaganiami
> sprzętowymi dwóch rozważanych modeli NER i przeglądem hostowanych API geokodujących.
>
> **Status:** częściowo zaimplementowane — krok NER działa: mikroserwis
> [`ner_service/`](../ner_service/README.md) (spaCy `pl_core_news_lg`) jest wdrożony
> na NAS i zintegrowany z backendem jako MVP (surowe encje `geogName`/`placeName`
> w tabeli `document_entities`, widoczne w UI) — patrz
> [`ner-integration-plan.md`](ner-integration-plan.md). Kroki 2-3 (weryfikacja
> Nominatim/LocationIQ + LLM, tagi `miejsce-*`) pozostają do zrobienia.
> **Ostatnia aktualizacja:** 2026-07-10 (status integracji; wcześniej 2026-07-09: weryfikacja przez Nominatim/OSM + przegląd hostowanych API)

## Problem

Obecny pipeline tagowania (`article_tagging.extract_countries_hybrid()`, patrz
[`backend/library/CLAUDE.md`](../backend/library/CLAUDE.md)) wykrywa **kraje** —
zamkniętą, stabilną listę ~197 państw — przez dopasowanie rdzeni słów
(`country_gazetteer.detect_countries()`) jako tani prescreen, a LLM tylko
potwierdza, które z kandydatów są faktycznie omawiane.

Artykuły geopolityczne regularnie wspominają też miejsca, które **nie są krajami**,
a mimo to są istotne kontekstowo: cieśniny (Cieśnina Ormuz, Bosfor), morza i zatoki
(Morze Czerwone, Zatoka Perska), regiony sporne (Górski Karabach, Pas Gazy,
Krym), pasma górskie, miasta strategiczne itd. Żaden z nich nie trafia dziś do
`doc.tags`.

## Dlaczego gazetteer (jak dla krajów) tu nie zadziała

Kraje są policzalną, zamkniętą listą — dlatego dało się je z góry wypisać i
dopasowywać rdzeniami słów bez żadnego modelu językowego. **Miejsca geograficzne
nie są zamkniętą listą** — cieśnin, mórz, regionów, pasm górskich i miast na
świecie są dziesiątki tysięcy, więc odpowiednik `country_gazetteer.py` byłby
niepraktyczny do utrzymania i zawsze niekompletny.

To zadanie z natury wymaga **rozpoznawania encji nazwanych (Named Entity
Recognition, NER)** — modelu, który potrafi wskazać nazwę własną miejsca w
dowolnym, wcześniej niewidzianym tekście, zamiast dopasowywać ją do zamkniętej
listy.

## Proponowane rozwiązanie: NER → weryfikacja faktu (Nominatim) → LLM ocenia istotność

Trzystopniowy pipeline, rozdzielający zadania zgodnie z tym, do czego każde
narzędzie faktycznie się nadaje — to zmodyfikowana wersja wzorca z krajów
(`extract_countries_hybrid`), z dodatkowym stopniem pośrednim:

1. **NER** (model uruchamiany lokalnie, bez LLM) skanuje tekst artykułu/streszczenia
   i wskazuje kandydatów — nazwane miejsca geograficzne. Tani, szybki, offline.
   Ma tendencję do fałszywych trafień (np. nazwa osoby błędnie oznaczona jako miejsce).
2. **Nominatim/OSM potwierdza fakt** — czy kandydat w ogóle rozwiązuje się na
   realny obiekt geograficzny. To pytanie **deterministyczne i faktograficzne**
   (istnieje / nie istnieje w bazie OSM), więc lepiej nadaje się do
   geokodera niż do LLM zgadującego "czy to brzmi jak miejsce". Odsiewa
   fałszywe trafienia z kroku 1 bez kosztu tokenów LLM. Szczegóły w sekcji
   [Weryfikacja przez Nominatim/OSM](#weryfikacja-przez-nominatimosm-zamiast-llm) poniżej.
3. **LLM ocenia istotność** — dopiero na już zweryfikowanej, zwykle znacznie
   krótszej liście kandydatów LLM rozstrzyga, które miejsca są *faktycznie
   omawiane* w artykule (nie tylko przelotnie wspomniane) — analogicznie do
   `COUNTRY_TAG_TRIGGERS`/`extract_countries_hybrid`. To jedyny krok, do
   którego LLM jest tu rzeczywiście potrzebny — ocena kontekstu/istotności,
   nie fakt istnienia miejsca.

Wynik trafia do `doc.tags` jako nowy namespace równoległy do `kraj-*`, np.
`miejsce-ciesnina-ormuz`, `miejsce-morze-czerwone`.

Miejsce integracji: analogicznie do `_apply_tags()` w
[`document_analysis_service.py`](../backend/library/document_analysis_service.py)
oraz `[w]`/`[k]` w `article_browser.py`.

**Poza zakresem tego planu:** wizualizacja tych miejsc na mapie (jak obecnie dla
krajów) — krok 2 (Nominatim) i tak zwraca współrzędne przy okazji weryfikacji,
więc geokodowanie pod mapę byłoby praktycznie "za darmo" jako efekt uboczny,
ale samo UI mapy to osobny, kolejny krok.

## Weryfikacja przez Nominatim/OSM (zamiast LLM)

### Co to jest

**PostGIS** to standardowe rozszerzenie przestrzenne PostgreSQL (typy
geometrii, indeksy przestrzenne, funkcje `ST_*`) — samo w sobie **nie zawiera
bazy nazw miejsc**, to tylko warstwa funkcjonalna pod zapytania przestrzenne.

Bazę nazw dostarcza **Nominatim** — oficjalne narzędzie geokodujące
OpenStreetMap, zbudowane na PostgreSQL+PostGIS. Importuje dane OSM (planeta
lub wycinek regionalny) do bazy i wystawia REST API do geokodowania (nazwa →
współrzędne) i odwrotnie. Dostępne jako oficjalne obrazy Dockera.

Dodatkowo przydatne: **`pg_trgm`** — rozszerzenie PostgreSQL do fuzzy-matchingu
tekstu (trigramy), pomocne przy niedokładnych zapytaniach (np. odmienione
„Cieśninie Ormuz" zamiast mianownika „Cieśnina Ormuz").

### Hostowane API (bez własnego sprzętu) — zweryfikowane 2026-07-09

| Usługa | Oparta na OSM/Nominatim? | Darmowy limit | Płatnie | Uwagi |
|---|---|---|---|---|
| [Publiczny Nominatim OSM](https://operations.osmfoundation.org/policies/nominatim/) | Tak (oficjalny) | — | — | Limit **1 zapytanie/s**, wymagany poprawny User-Agent/Referer, skrypty masowe ograniczone do 4 zap./min z jednej maszyny + obowiązkowy cache. **Zabronione użycie komercyjne/odsprzedaż geokodowania** — polityka wprost mówi, że aplikacje, których głównym zastosowaniem jest geokodowanie, "muszą uruchomić własną usługę". Serwery utrzymywane z darowizn, "bardzo ograniczona pojemność" |
| [LocationIQ](https://locationiq.com/pricing) | **Tak, wprost oparte na Nominatim/API-kompatybilne** | 5 000 zapytań/dzień, 2 zap./s | Od ~$45-50/mies. (~10k/dzień) do ~$950/mies. (30M/mies.), enterprise custom | Użycie komercyjne dozwolone (z linkiem atrybucyjnym) — **najbliższy odpowiednik "Nominatim jako usługa"** |
| [Geoapify](https://www.geoapify.com/openstreetmap-geocoding/) | Częściowo (OSM + GeoNames + OpenAddresses + GTFS) | 3 000 kredytów/dzień (~90k/mies.), w tym darmowy geocoding wsadowy | — | Nie czysty OSM/Nominatim, ale generous free tier |
| [OpenCage](https://opencagedata.com/pricing) | Częściowo (agreguje Nominatim + OSM + GeoNames + inne) | 2 500 zapytań/dzień | — | Darmowy limit jawnie opisany jako **trial do testów, nie darmowy tier produkcyjny** |
| [Photon (komoot)](https://github.com/komoot/photon) | Tak (inny silnik niż Nominatim, też na danych OSM) | Publiczna instancja ~1 zap./s, "intensywne użycie" throttlowane/banowane | — | Komoot nie oferuje płatnego API; **do rozważenia głównie jako self-host** (patrz niżej) |

**Wniosek praktyczny:** dla umiarkowanej skali (dziesiątki kandydatów per
artykuł, przetwarzanie wsadowe/asynchroniczne, nie real-time) **darmowy tier
LocationIQ (5 000/dzień) prawdopodobnie w zupełności wystarczy** — bez potrzeby
zakupu jakiegokolwiek sprzętu na start. Self-hosting ma sens dopiero przy
naprawdę dużej skali albo chęci pełnej niezależności od zewnętrznego API.

### Self-hosting: Nominatim vs Photon

Jeśli mimo wszystko self-hosting — **Photon (komoot) jest dramatycznie
lżejszy niż Nominatim** dla tego samego zadania (czy nazwa istnieje jako
miejsce w OSM):

| | Nominatim (self-host) | Photon (self-host) |
|---|---|---|
| Dysk (pełna planeta) | **~800 GB+** | **~95 GB** |
| RAM (import) | 64-128 GB | 64 GB zalecane |
| Dysk (wycinek regionalny, np. Europa+MENA+Azja) | ~10-50 GB | proporcjonalnie mniej |
| Silnik | PostgreSQL + PostGIS | Elasticsearch/Lucene (własny indeks) |

Photon nie jest literalnie "Nominatim" (inny silnik wyszukiwania), ale
rozwiązuje ten sam problem (czy string to realne miejsce z OSM) przy
znacznie niższych wymaganiach dyskowych — wart rozważenia jako pierwszy
kandydat do self-hostingu, jeśli/kiedy darmowe API przestaną wystarczać.

## Porównanie modeli NER

### Opcja 1: spaCy `pl_core_news_lg` (rekomendowana na start)

Model spaCy dla języka polskiego, trenowany na korpusie NKJP. Ma etykiety
**inne niż standardowe angielskie modele** — zamiast ogólnego `LOC`/`GPE`
rozróżnia:
- `geogName` — cechy geograficzne (cieśniny, morza, rzeki, pasma górskie) — **to jest dokładnie to, czego szukamy**
- `placeName` — miejsca administracyjne (miasta, regiony, kraje)
- plus `persName`, `orgName`, `date`, `time` itd.

To rozróżnienie oznacza, że nie trzeba nic dodatkowo klasyfikować — model sam
oddziela "cechę geograficzną" od "miejsca administracyjnego".

**Instalacja** (zgodnie z konwencją projektu — `uv`, nigdy `pip`):

```bash
cd backend
uv add spacy
uv run python -m spacy download pl_core_news_lg
```

(`spacy download` samo w sobie używa `pip` pod spodem tylko do pobrania paczki
modelu — to jest udokumentowany, standardowy sposób dystrybucji modeli spaCy,
inny niż ręczne `pip install` zależności projektu, i nie koliduje z regułą
"nigdy pip" dla `pyproject.toml`).

Sprawdzenie działania:

```python
import spacy
nlp = spacy.load("pl_core_news_lg")
doc = nlp("Napięcia w Cieśninie Ormuz rosną po ataku na tankowiec.")
for ent in doc.ents:
    print(ent.text, ent.label_)
# Cieśninie Ormuz  geogName
```

**Wymagania sprzętowe:**

| Zasób | Wymaganie |
|---|---|
| CPU | Dowolny współczesny x86_64 (nie ARM — wheel'e Cython dla spaCy są budowane pod x86_64/arm64, ale wydajność na słabszych CPU niższa) |
| RAM | ~1-2 GB wolnego (model + pipeline w pamięci) |
| GPU | **Niepotrzebne.** Pipeline `lg` jest oparty na sieciach CNN, nie transformerach — CPU wystarcza |
| Dysk | ~500-600 MB na model |
| Szybkość | Pojedynczy artykuł (kilka tysięcy słów) — rzędu **ułamka sekundy do ~2 sekund** na współczesnym CPU serwerowym/desktopowym |

**Wniosek:** obecny NAS (QNAP TS-453Be, Intel Celeron, x86_64, bez GPU) powinien
obsłużyć tę opcję bez żadnego nowego sprzętu.

Wariant `pl_core_news_trf` (oparty na transformerze zamiast CNN) daje wyższą
dokładność kosztem znacznie wolniejszej inferencji na CPU (rząd wielkości
10-50× wolniej niż `lg`) — do rozważenia dopiero jeśli jakość `lg` okaże się
niewystarczająca, i wtedy wymagania zbliżają się do Opcji 2 poniżej.

### Opcja 2: HerBERT (Allegro) + fine-tune pod NER

Polski model typu BERT (transformer), trenowany przez Allegro; warianty
fine-tunowane pod NER dostępne na HuggingFace (ekosystem CLARIN-PL/Allegro).
Zwykle wyższa surowa dokładność niż spaCy `lg`, ale znacznie cięższy.

**Instalacja:**

```bash
cd backend
uv add transformers torch
```

Użycie (przykład, dokładna nazwa modelu do zweryfikowania na HuggingFace w
momencie wdrożenia — ekosystem NER dla HerBERT się rozwija):

```python
from transformers import pipeline
ner = pipeline("ner", model="<nazwa-modelu-herbert-ner>", aggregation_strategy="simple")
results = ner("Napięcia w Cieśninie Ormuz rosną po ataku na tankowiec.")
```

**Wymagania sprzętowe:**

| Zasób | Wymaganie |
|---|---|
| CPU | Możliwe, ale **wolne** — kilka do kilkunastu sekund na fragment tekstu dla wariantu `base` na współczesnym CPU wielordzeniowym; wariant `large` jeszcze wolniej |
| GPU | **Mocno rekomendowane** dla sensownej przepustowości (batch przetwarzanie wielu dokumentów/chunków). Wystarczy karta klasy wejściowej/średniej — model BERT-base to ~110-125M parametrów, inferencja mieści się w kilku GB VRAM. Przykładowo: NVIDIA RTX 3060 12GB, RTX 4060, a nawet starsze RTX 2060/GTX 1660 6GB — **nie jest potrzebna karta wysokiej klasy** |
| RAM (system) | 16 GB+ zalecane (PyTorch + zależności to same w sobie ~2-4 GB) |
| Dysk | ~2 GB na PyTorch + kilkaset MB do ~1.5 GB na wagi modelu (zależnie od wariantu base/large) |
| CUDA | Tylko NVIDIA praktycznie ma sens — AMD ROCm jest gorzej wspierany przez PyTorch, szczególnie pod Windows |

**Wniosek:** obecny NAS (Celeron, bez GPU) **nie jest dobrym kandydatem** do
uruchamiania tej opcji z sensowną przepustowością. Jeśli hardware ma być
kupowany pod tę opcję: priorytet to GPU NVIDIA z ~6-12 GB VRAM (karta
konsumencka wystarczy, nie trzeba serwerowej/profesjonalnej), 16 GB+ RAM
systemowego, CPU dowolny współczesny x86_64.

## Wymagania sprzętowe — podsumowanie

| | Opcja 1: spaCy `pl_core_news_lg` | Opcja 2: HerBERT NER | Weryfikacja (Nominatim/OSM) |
|---|---|---|---|
| Nowy sprzęt potrzebny? | **Nie** — działa na obecnym NAS | **Tak, praktycznie** — GPU NVIDIA zalecane | **Nie na start** — hostowane API (LocationIQ free tier) |
| GPU | Niepotrzebne | Zalecane, 6-12 GB VRAM wystarczy (karta konsumencka) | Niepotrzebne |
| RAM | ~1-2 GB | 16 GB+ (system), model ~1-2 GB | — (zewnętrzne API) lub 8-16 GB przy self-hostingu wycinka regionalnego |
| Dysk | ~500-600 MB | ~2 GB + wagi modelu | — (API) / ~10-50 GB (self-host, wycinek) / ~800 GB Nominatim vs ~95 GB Photon (pełna planeta) |
| Szybkość (per artykuł) | Ułamek sekundy — ~2 s (CPU) | Kilka-kilkanaście s (CPU) / <1 s (GPU) | Zależna od API/limitu (np. 2 zap./s LocationIQ) |
| Dokładność | Dobra, specyficzna dla PL (`geogName` vs `placeName`) | Zwykle wyższa niż spaCy `lg` | Deterministyczna — "istnieje w OSM" tak/nie |
| Złożoność integracji | Niska | Średnia (transformers + torch, cięższe zależności) | Niska (REST API) |

## Rekomendacja

Zacząć od **Opcji 1 (spaCy `pl_core_news_lg`)** jako generatora kandydatów —
nie wymaga zakupu nowego sprzętu, prosta integracja, wbudowane rozróżnienie
`geogName`/`placeName` idealnie pasujące do problemu.

Do **weryfikacji faktu** użyć **hostowanego API (LocationIQ, darmowy tier
5 000 zapytań/dzień)** zamiast od razu inwestować w self-hosting Nominatim/Photon
— przy realistycznej skali (dziesiątki kandydatów per artykuł, przetwarzanie
asynchroniczne) darmowy tier prawdopodobnie wystarczy na długo. Self-hosting
(i wtedy raczej Photon niż Nominatim — ~95 GB vs ~800 GB dysku dla pełnej
planety) ma sens dopiero, gdy/jeśli wolumen realnie to uzasadni.

**LLM** wchodzi do gry dopiero na końcu — ocenia istotność już zweryfikowanych
kandydatów, więc nie musi analizować całego surowego tekstu pod kątem "czy to
w ogóle miejsce".

Opcja 2 (HerBERT zamiast spaCy do samego NER) warta rozważenia jako upgrade
później, jeśli jakość Opcji 1 okaże się niewystarczająca w praktyce — i to jest
właściwy moment, żeby myśleć o zakupie GPU (karta konsumencka klasy RTX
3060/4060 12GB w zupełności wystarczy, nie trzeba inwestować w sprzęt
data-center'owy).

**Podsumowując pod kątem zakupu sprzętu:** ten plan, w proponowanym kształcie
(spaCy + hostowane API + LLM), **nie wymaga żadnego nowego sprzętu na start**.
Ewentualny GPU (Opcja 2) lub dysk pod self-hosted geokoder (Photon/Nominatim)
to decyzje odroczone do momentu, gdy darmowe/tanie opcje przestaną wystarczać.

## Otwarte pytania / dalsze kroki

- Jaki namespace tagów dla miejsc — `miejsce-*`? `geo-*`? Do ustalenia przy implementacji.
- Czy tagować tylko `geogName`, czy też `placeName` (miasta) — ryzyko dużej liczby tagów per artykuł przy miastach.
- Wybór dokładnej nazwy modelu HerBERT-NER na HuggingFace w momencie wdrożenia (ekosystem się zmienia).
- Dokładna weryfikacja aktualnego cennika LocationIQ przed wdrożeniem (widoczne niespójności między źródłami w momencie pisania tego planu — sprawdzić `locationiq.com/pricing` na bieżąco).
- Wizualizacja miejsc na mapie — krok weryfikacji (Nominatim/LocationIQ) zwraca współrzędne przy okazji, więc dane pod mapę byłyby "przy okazji", ale samo UI to osobny temat.
- Brak wpisu w backlogu (`_bmad-output/planning-artifacts/epics/backlog.md`) — dodać jako osobne zadanie, gdy będzie gotowość do implementacji.
