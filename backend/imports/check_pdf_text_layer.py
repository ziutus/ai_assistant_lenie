"""Check whether a PDF has a usable text layer or needs OCR.

Extracts text page-by-page with pypdf and reports how many pages come back
empty/near-empty. A high empty-page ratio means the PDF is scanned images
without embedded text, so it should go through test_code/ocr_mistral.py
(Mistral OCR) instead. A low ratio means the text layer is usable directly.

Does not touch the Lenie database.
"""

import argparse
import sys

from pypdf import PdfReader

EMPTY_THRESHOLD = 10  # chars; below this a page counts as "empty" (likely a scanned image)
LOW_THRESHOLD = 100  # chars; below this (but >= EMPTY_THRESHOLD) a page counts as "low"


def analyze_pdf(file_path: str, sample: int | None = None) -> dict:
    reader = PdfReader(file_path)
    total_pages = len(reader.pages)
    indices = range(total_pages)
    if sample and sample < total_pages:
        step = total_pages / sample
        indices = sorted({int(i * step) for i in range(sample)})

    per_page_chars = []
    for i in indices:
        text = reader.pages[i].extract_text() or ""
        per_page_chars.append(len(text.strip()))

    checked = len(per_page_chars)
    empty_pages = sum(1 for c in per_page_chars if c < EMPTY_THRESHOLD)
    low_pages = sum(1 for c in per_page_chars if EMPTY_THRESHOLD <= c < LOW_THRESHOLD)
    good_pages = checked - empty_pages - low_pages
    total_chars = sum(per_page_chars)
    empty_ratio = empty_pages / checked if checked else 0.0

    if empty_ratio > 0.5:
        verdict = "OCR_NEEDED"
    elif empty_ratio > 0.2:
        verdict = "UNCERTAIN"
    else:
        verdict = "TEXT_LAYER_OK"

    return {
        "file_path": file_path,
        "total_pages": total_pages,
        "checked_pages": checked,
        "empty_pages": empty_pages,
        "low_pages": low_pages,
        "good_pages": good_pages,
        "total_chars": total_chars,
        "avg_chars_per_page": total_chars / checked if checked else 0.0,
        "empty_ratio": empty_ratio,
        "verdict": verdict,
    }


def print_report(stats: dict) -> None:
    print(f"Plik: {stats['file_path']}")
    print(f"Stron w PDF: {stats['total_pages']} (sprawdzono: {stats['checked_pages']})")
    print(f"Srednio znakow/strone: {stats['avg_chars_per_page']:.0f}")
    print(
        f"Puste strony (<{EMPTY_THRESHOLD} zn.): {stats['empty_pages']} "
        f"({stats['empty_ratio']:.0%})"
    )
    print(f"Ubogie strony (<{LOW_THRESHOLD} zn.): {stats['low_pages']}")
    print(f"Strony z tekstem: {stats['good_pages']}")
    print()
    if stats["verdict"] == "OCR_NEEDED":
        print("WERDYKT: PDF wyglada na skan bez warstwy tekstowej -> potrzebny OCR.")
        print("Uruchom: python backend/test_code/ocr_mistral.py --input-dir <katalog z PDF>")
    elif stats["verdict"] == "UNCERTAIN":
        print("WERDYKT: NIEJEDNOZNACZNIE - czesc stron bez tekstu. Sprawdz recznie probke stron")
        print("(np. python imports/check_pdf_text_layer.py <plik> --show-sample) przed decyzja o OCR.")
    else:
        print("WERDYKT: PDF ma uzywalna warstwe tekstowa -> OCR niepotrzebny,")
        print("mozna wyciagnac tekst bezposrednio przez pypdf.")


def show_sample(file_path: str, n: int = 5) -> None:
    reader = PdfReader(file_path)
    total = len(reader.pages)
    step = max(total // n, 1)
    for i in range(0, total, step):
        text = reader.pages[i].extract_text() or ""
        print(f"=== strona {i} ({len(text)} znakow) ===")
        print(text[:400])
        print()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("file", help="sciezka do pliku PDF")
    parser.add_argument(
        "--sample",
        type=int,
        default=None,
        help="sprawdz tylko N rownomiernie rozlozonych stron zamiast calego pliku (szybszy podglad dla duzych PDF-ow)",
    )
    parser.add_argument(
        "--show-sample",
        type=int,
        default=0,
        metavar="N",
        help="wypisz tresc N przykladowych stron (do recznej oceny jakosci ekstrakcji)",
    )
    args = parser.parse_args()

    stats = analyze_pdf(args.file, sample=args.sample)
    print_report(stats)

    if args.show_sample:
        print()
        show_sample(args.file, args.show_sample)

    sys.exit(0 if stats["verdict"] == "TEXT_LAYER_OK" else 1)


if __name__ == "__main__":
    main()
