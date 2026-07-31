# Porównanie bibliotek do ekstrakcji tekstu z PDF

> Decyzja i jej uzasadnienie (licencja AGPL PyMuPDF vs. BSL 1.1 projektu,
> warunek rewizji przed SaaS) są sformalizowane w
> [ADR-019](adr/adr-019-pymupdf-agpl-license.md) — ten dokument to pełna
> analiza porównawcza, na którą ADR się powołuje.

Kontekst: import książek PDF do Lenie (`backend/library/book_pdf_import.py`,
`backend/imports/book_import_pdf_twierdza_linux.py`, `backend/imports/check_pdf_text_layer.py`).
Porównanie zrobione 2026-07-27 na realnej książce technicznej ("Twierdza Linux.
Bezpieczeństwo dla dociekliwych", Karol Szafrański, Sekurak) — 539 stron, dużo
list punktowanych i bloków kodu/configu przeplecionych z prozą.

## Wynik: używamy PyMuPDF (fitz)

Zaimplementowane w `book_pdf_import.py`. Powody:

- **Jawny miękki łącznik `\xad` (U+00AD, soft hyphen)** przy dzieleniu wyrazów na
  końcu linii. `pypdf` zwraca w tym miejscu zwykły myślnik czasem poprzedzony
  dodatkową spacją (`"wy -\nkorzystywane"`) — trzeba zgadywać regexem, czy to
  faktyczne dzielenie wyrazu czy prawdziwy myślnik. PyMuPDF mówi to wprost:
  `"wy\xad\nkorzystywane"` → deterministyczne `text.replace("\xad\n", "")`.
- **Poprawnie wstawia `\n` między wizualnie ułożonymi jeden pod drugim elementami
  tekstu.** `pypdf` potrafił skleić dwie sąsiednie linie bez żadnego separatora
  (np. tytuł rozdziału 2 wyszedł jako `"OPROGRAMOWANIAMIT BEZPIECZEŃSTWA"` —
  dwa różne nagłówki złączone w jedno słowo). PyMuPDF (plain `page.get_text()`)
  tego nie robi.
- **Poprawnie odczytuje font "small caps"** jako tekst o rzeczywistej mieszanej
  wielkości liter. Ten sam wyraz w tej samej książce bywał wersalikami na
  stronie startowej rozdziału i mieszaną wielkością liter w żywej paginie —
  `pypdf` normalizował oba warianty do wersalików, PyMuPDF zwraca prawdziwe
  znaki spod fontu (trzeba dopisać `(?i)` do regexów dopasowujących markery,
  jeśli się na tym polega).

### Zastrzeżenie licencyjne — WAŻNE

**PyMuPDF jest na licencji AGPL-3.0 (albo płatnej licencji komercyjnej od
Artifex).** AGPL wymaga udostępnienia pełnego kodu źródłowego aplikacji na
żądanie każdego, kto korzysta z niej **przez sieć** (nie tylko przy dystrybucji
binarki) — to bezpośrednio dotyczy Lenie, bo działa jako serwer używany przez
przeglądarkę/API.

Decyzja z 2026-07-27: **PyMuPDF jest OK dopóki Lenie pozostaje prywatną,
niekomercyjną instalacją domową** (obecny zakres — patrz
`docs/deployment/nas/multi-user-household.md`) — koliduje formalnie z modelem
BSL 1.1 projektu (`LICENSE`), ale ryzyko praktyczne jest znikome przy
korzystaniu tylko przez zaufanych domowników na własnym NAS.

**Zanim Lenie stanie się usługą hostowaną/SaaS dla obcych użytkowników
(`docs/deployment/commercial-multi-tenant-scaling-experiment.md`), tę decyzję
trzeba przemyśleć od nowa** — patrz notatka w prywatnym repo
(`lenie-bmad-private/docs/`) o rewizji przed komercjalizacją. Opcje na wtedy:
płatna licencja komercyjna PyMuPDF, albo migracja na `pdfplumber` (patrz niżej)
kosztem gorszej jakości ekstrakcji list/kodu.

## Porównane biblioteki

| Biblioteka | Licencja | Plusy | Minusy |
|---|---|---|---|
| **pypdf** | BSD-3 | już było w projekcie (CV parsing w `test_code/`), OK jakość ogólna | (1) czasem brak `\n` między wizualnie ułożonymi elementami — sklejone słowa bez separatora; (2) dzielenie wyrazów niespójne (czasem spacja przed myślnikiem, czasem nie) — fragile regex do dehyfenizacji; (3) normalizuje small-caps do pełnych wersalików, tracąc informację o prawdziwej wielkości liter |
| **pdfplumber** | MIT | czyste łączenie linii (bez buga sklejania), czysty myślnik przy dzieleniu wyrazów (bez dodatkowej spacji) | zjada wielokrotne spacje przy rekonstrukcji linii — wyrównanie kolumn w blokach kodu/configu znika (np. `"glowna_crypt  UUID=...  none  luks"` → `"glowna_crypt UUID=... none luks"`); `extract_text(layout=True)` dodaje wcięcia symulujące pozycję kolumny, ale nadal gubi wewnętrzne odstępy |
| **PyMuPDF (fitz)** | AGPL-3.0 / komercyjna | patrz wyżej — najlepsza jakość techniczna ekstrakcji tekstu | licencja (patrz zastrzeżenie); tryb `get_text("blocks")` (grupowanie w akapity przez geometrię strony) jest niespójny — dla czystej prozy poprawnie łączy całą wielolinijkową klauzulę w jeden blok, ale dla list punktowanych/kodu **cicho gubi powtarzające się żywe paginy** (znaleziono empirycznie: `get_text()` zwykły znajduje 8 wystąpień markera rozdziału na stronę, `get_text("blocks")` tylko 1 w całej książce) — dlatego finalnie używamy `get_text()` per-strona, nie `"blocks"` |

## Problem, którego żadna biblioteka nie rozwiązuje automatycznie

**Odróżnienie zawinięcia linii (word wrap) od prawdziwego końca akapitu.**
Wszystkie trzy biblioteki zwracają dokładnie jeden `\n` zarówno między
zawiniętymi liniami tego samego akapitu, jak i między dwoma różnymi akapitami —
żadna nie oznacza tego jednoznacznie. Renderer markdown traktuje pojedynczy
`\n` jako miękkie złamanie (renderuje się jako spacja, bez wizualnej przerwy),
więc bez dodatkowej heurystyki cała treść rozdziału wygląda jak jedna ściana
tekstu.

Sprawdzono też podejście geometryczne (współrzędne linii przez
`page.get_text("dict")`, odstępy pionowe między liniami) — działa dobrze dla
czystej prozy (spójny odstęp ~-3.9pt wewnątrz akapitu vs. +8pt między
akapitami), ale zawodzi dla list punktowanych i callout-boxów w tej książce:
odstęp między kontynuacją tego samego punktu listy a początkiem NASTĘPNEGO
punktu bywa taki sam (~0.8pt) jak odstęp wewnątrz jednego punktu — geometria
strony nie daje tu jednoznacznego sygnału, tylko sama treść (glif `▶`/`✅` na
początku linii) pozwala rozróżnić nowy element listy.

**Rozwiązanie przyjęte w `book_pdf_import.py`:** bezpieczna, addytywna
heurystyka tekstowa (`_insert_paragraph_breaks()`) — wstawia dodatkową pustą
linię po linii, która jest **krótsza niż typowa szerokość wiersza na stronie
ORAZ kończy się interpunkcją kończącą zdanie** (mocny sygnał końca akapitu), a
także zawsze przed początkiem punktu listy (`▶`, `✅`, `1.` itp.). Nigdy nic nie
scala ani nie usuwa, więc bloki kodu/configu (częste w książkach technicznych)
nigdy nie zostają rozerwane, nawet gdy heurystyka nie wykryje jakiejś granicy.

## Dla przyszłych importów książek

- Każda książka dostaje własny cienki skrypt CLI
  `imports/book_import_pdf_<slug>.py` (np. `book_import_pdf_twierdza_linux.py`)
  ze swoimi stałymi (tytuł, autor, `--chapter-regex`,
  `--heading-font-prefix`/`--heading-min-size`) — silnik w
  `library/book_pdf_import.py` jest generyczny, parametryzowany (patrz
  `backend/imports/CLAUDE.md`).
- Jeśli tekst nadal wygląda jak ściana tekstu mimo `_insert_paragraph_breaks()`,
  prawdopodobnie ta konkretna książka ma inny styl typograficzny (np. inne
  znaki końca zdania, brak wcięć/bulletów) — heurystykę trzeba będzie
  dostroić per-book, podobnie jak `book_normalize.py` robi to dla map
  rozdziałów przy książkach z OCR.
- `check_pdf_text_layer.py` nadal używa `pypdf` (wystarcza do samej diagnostyki
  "czy jest warstwa tekstowa" — nie trzeba tam jakości PyMuPDF).
