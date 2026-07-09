# Rozpoznawanie miejsc geograficznych w tekstach (NER) — plan na przyszłość

> Plan techniczny: problem tagowania miejsc geograficznych (cieśniny, morza, regiony,
> pasma górskie, miasta) wykraczających poza obecny, zamknięty gazetteer krajów
> ([`country_gazetteer.py`](../backend/library/country_gazetteer.py)), proponowane
> rozwiązanie oraz wymagania sprzętowe dwóch rozważanych modeli NER.
>
> **Status:** plan / do przemyślenia — nieprzypisane do backlogu, nic nie zaimplementowane.
> **Ostatnia aktualizacja:** 2026-07-09

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

## Proponowane rozwiązanie: NER jako generator kandydatów + potwierdzenie LLM

Ten sam wzorzec architektoniczny co przy krajach (`extract_countries_hybrid`),
tylko ze zmienionym źródłem kandydatów:

1. **NER** (model uruchamiany lokalnie, bez LLM) skanuje tekst artykułu/streszczenia
   i wskazuje kandydatów — nazwane miejsca geograficzne. Tani, szybki, offline.
2. **LLM potwierdza** (analogicznie do `COUNTRY_TAG_TRIGGERS`/`extract_countries_hybrid`),
   które z kandydatów są *faktycznie istotne* w artykule (nie tylko przelotnie
   wspomniane), i odrzuca fałszywe trafienia modelu NER.
3. Wynik trafia do `doc.tags` jako nowy namespace równoległy do `kraj-*`, np.
   `miejsce-ciesnina-ormuz`, `miejsce-morze-czerwone`.

Miejsce integracji: analogicznie do `_apply_tags()` w
[`document_analysis_service.py`](../backend/library/document_analysis_service.py)
oraz `[w]`/`[k]` w `article_browser.py`.

**Poza zakresem tego planu:** wizualizacja tych miejsc na mapie (jak obecnie dla
krajów) wymagałaby dodatkowo geokodowania nazwy na współrzędne (np. Nominatim,
darmowe API OSM, limit 1 zapytanie/s — do cache'owania w bazie per nazwa
miejsca). To osobny, kolejny krok.

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

| | Opcja 1: spaCy `pl_core_news_lg` | Opcja 2: HerBERT NER |
|---|---|---|
| Nowy sprzęt potrzebny? | **Nie** — działa na obecnym NAS | **Tak, praktycznie** — GPU NVIDIA zalecane |
| GPU | Niepotrzebne | Zalecane, 6-12 GB VRAM wystarczy (karta konsumencka) |
| RAM | ~1-2 GB | 16 GB+ (system), model ~1-2 GB |
| Szybkość (per artykuł) | Ułamek sekundy — ~2 s (CPU) | Kilka-kilkanaście s (CPU) / <1 s (GPU) |
| Dokładność | Dobra, specyficzna dla PL (`geogName` vs `placeName`) | Zwykle wyższa niż spaCy `lg` |
| Złożoność integracji | Niska | Średnia (transformers + torch, cięższe zależności) |

## Rekomendacja

Zacząć od **Opcji 1 (spaCy `pl_core_news_lg`)** — nie wymaga zakupu nowego
sprzętu, prosta integracja, wbudowane rozróżnienie `geogName`/`placeName`
idealnie pasujące do problemu, a jakość jako *generator kandydatów* (z LLM jako
finalnym sitem precyzji, tak jak przy krajach) nie musi być perfekcyjna — LLM i
tak odrzuci fałszywe trafienia.

Opcja 2 (HerBERT) warta rozważenia jako upgrade później, jeśli jakość Opcji 1
okaże się niewystarczająca w praktyce — i to jest właściwy moment, żeby myśleć
o zakupie GPU (karta konsumencka klasy RTX 3060/4060 12GB w zupełności
wystarczy, nie trzeba inwestować w sprzęt data-center'owy).

## Otwarte pytania / dalsze kroki

- Jaki namespace tagów dla miejsc — `miejsce-*`? `geo-*`? Do ustalenia przy implementacji.
- Czy tagować tylko `geogName`, czy też `placeName` (miasta) — ryzyko dużej liczby tagów per artykuł przy miastach.
- Wybór dokładnej nazwy modelu HerBERT-NER na HuggingFace w momencie wdrożenia (ekosystem się zmienia).
- Geokodowanie do wizualizacji na mapie — osobny temat, nie objęty tym planem.
- Brak wpisu w backlogu (`_bmad-output/planning-artifacts/epics/backlog.md`) — dodać jako osobne zadanie, gdy będzie gotowość do implementacji.
