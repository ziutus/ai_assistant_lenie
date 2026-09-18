# OCR zeskanowanych dokumentów — podejście i wybór narzędzia

Kontekst: OCR (rozpoznawanie tekstu z obrazu/skanu) jest potrzebne przy
imporcie zeskanowanych książek/dokumentów PDF, które nie mają warstwy
tekstowej (`backend/imports/check_pdf_text_layer.py` wykrywa ten przypadek).
Nie mylić z `book_pdf_import.py`/PyMuPDF — to ekstrakcja tekstu z PDF, które
**już mają** warstwę tekstową (patrz [`pdf-library-comparison.md`](pdf-library-comparison.md)).
OCR wchodzi do gry dopiero, gdy tej warstwy nie ma (czysty skan/obraz).

## Aktualne podejście: Mistral OCR API

`backend/test_code/ocr_mistral.py` — skrypt eksperymentalny (jeszcze nie
promowany do `imports/`, patrz [`backend/test_code/CLAUDE.md`](../backend/test_code/CLAUDE.md))
wysyłający zeskanowane PDF-y do `mistral-ocr-latest` i zapisujący wynik jako
Markdown.

- **Dwa tryby**: standardowy (synchroniczny, plik po pliku, ~$2/1000 stron)
  i batch (asynchroniczny przez Mistral Batch API, ~$1/1000 stron — 50%
  taniej, ale wynik dostępny po minutach/godzinach)
- Cache po nazwie pliku (`.ocr_cache.json`) — nie płaci się dwa razy za ten
  sam skan
- `--dry-run` pokazuje szacowany koszt przed wysłaniem czegokolwiek do API

## Dlaczego NIE lokalny OCR (Tesseract / QNAP OCR Converter)

QNAP TS-453Be (NAS produkcyjny Lenie) miał zainstalowaną aplikację **OCR
Converter** z App Center — bazuje na silniku open-source **Tesseract**.
Usunięta 2026-09-18 (była zainstalowana, ale nigdy faktycznie nieużywana:
`Enable=FALSE`, zero uruchomień — patrz prywatny runbook NAS-a).

**Skuteczność Tesseract dla języka polskiego jest zbyt słaba do realnego
użycia w tym projekcie:**

- Aktualny benchmark (Tesseract 5.5.1) pokazuje **CER (Character Error
  Rate) na poziomie 26,3%** dla tekstu polskiego — mniej więcej co czwarty
  znak błędny
- Standardowe modele OCR trenowane głównie na korpusach angielskich
  systematycznie mylą polskie znaki diakrytyczne: **ą↔a, ł↔l, ó↔o** — a
  pominięty "ogonek" potrafi odwrócić sens zdania
- Dla starszych/historycznych polskich dokumentów (czcionki
  gotyckie/frakturowe) dokładność spada jeszcze bardziej

Przy tym poziomie błędów tekst wymagałby tak intensywnej ręcznej korekty,
że lokalny OCR nie daje realnej oszczędności czasu względem płatnego API o
wyższej jakości. Stąd decyzja o Mistral OCR zamiast Tesseract/QNAP OCR
Converter — mimo kosztu per-strona, jakość rozpoznawania jest wystarczająco
wyższa, żeby uzasadnić wydatek przy imporcie książek.

**Jeśli w przyszłości potrzebny będzie OCR offline/bez kosztu per-strona**,
rozważyć dedykowany model `pol.traineddata` z repozytorium
[`tesseract-ocr/tessdata_best`](https://github.com/tesseract-ocr/tessdata_best)
(najlepsze dostępne wagi LSTM dla Tesseract) zamiast domyślnego modelu — to
nie było testowane w tym projekcie i może dać wyraźnie lepszy wynik niż
26,3% CER, ale nadal prawdopodobnie gorszy niż komercyjne API (Mistral,
Google Vision, Azure OCR).

## Źródła

- Tesseract Polish CER 26,3% (v5.5.1): [Najlepszy OCR Polski 2026 — CodeSOTA](https://www.codesota.com/polish-ocr)
- Silnik QNAP OCR Converter: [QNAP — How to Use OCR Converter](https://www.qnap.com/en/how-to/tutorial/article/how-to-use-ocr-converter-to-recognize-and-extract-text-from-images)
- Wagi modelu polskiego: [tesseract-ocr/tessdata_best — pol.traineddata](https://github.com/tesseract-ocr/tessdata_best/blob/main/pol.traineddata)
