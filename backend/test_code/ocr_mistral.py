#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
OCR zeskanowanych książek (PDF) za pomocą Mistral OCR API.

Tryby pracy:
  1. STANDARD (domyślny) — synchroniczne wywołania API, plik po pliku
  2. BATCH — asynchroniczne przetwarzanie przez Mistral Batch API (50% taniej)

Użycie:
    export MISTRAL_API_KEY="your-api-key"

    # Tryb standardowy — plik po pliku
    python ocr_mistral.py --combine

    # Tryb batch — tańszy, ale asynchroniczny (minuty/godziny)
    python ocr_mistral.py --batch submit          # Wyślij zadanie
    python ocr_mistral.py --batch status           # Sprawdź postęp
    python ocr_mistral.py --batch download         # Pobierz wyniki

    # Podgląd bez kosztów
    python ocr_mistral.py --dry-run

Opcje:
    --input-dir DIR    Katalog z plikami PDF (domyślnie: bieżący)
    --output-dir DIR   Katalog wyjściowy (domyślnie: markdown_ocr)
    --pattern GLOB     Wzorzec plików (domyślnie: IMG_*.pdf)
    --combine          Połącz wyniki w jeden plik _cala_ksiazka.md
    --batch ACTION     Tryb batch: submit / status / download
    --dry-run          Pokaż plan bez wysyłania do API
"""

import argparse
import base64
import json
import os
import sys
import time
from io import BytesIO
from pathlib import Path

try:
    from mistralai.client import Mistral
except ImportError:
    try:
        from mistralai import Mistral
    except ImportError:
        print("Brak pakietu mistralai. Zainstaluj: pip install mistralai")
        sys.exit(1)


MODEL = "mistral-ocr-latest"
CACHE_FILE = ".ocr_cache.json"
BATCH_STATE_FILE = ".ocr_batch_state.json"


# ──────────────────────────────────────────────
# Cache (wspólny dla obu trybów)
# ──────────────────────────────────────────────

def load_cache(output_dir: Path) -> dict:
    cache_path = output_dir / CACHE_FILE
    if cache_path.exists():
        with open(cache_path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_cache(output_dir: Path, cache: dict):
    cache_path = output_dir / CACHE_FILE
    with open(cache_path, "w", encoding="utf-8") as f:
        json.dump(cache, f, indent=2)


# ──────────────────────────────────────────────
# Batch state (śledzenie zadania batch)
# ──────────────────────────────────────────────

def load_batch_state(output_dir: Path) -> dict:
    path = output_dir / BATCH_STATE_FILE
    if path.exists():
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_batch_state(output_dir: Path, state: dict):
    path = output_dir / BATCH_STATE_FILE
    with open(path, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2)


# ──────────────────────────────────────────────
# Wspólne
# ──────────────────────────────────────────────

def encode_pdf(pdf_path: Path) -> str:
    with open(pdf_path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")


def get_pdf_files(input_dir: Path, pattern: str) -> list[Path]:
    return sorted(input_dir.glob(pattern))


def combine_markdown(pdf_files: list[Path], output_dir: Path):
    """Połącz poszczególne pliki .md w jeden."""
    combined_path = output_dir / "_cala_ksiazka.md"
    print(f"\nŁączenie w {combined_path}...")

    parts = []
    for pdf_file in pdf_files:
        md_file = output_dir / f"{pdf_file.stem}.md"
        if md_file.exists():
            with open(md_file, "r", encoding="utf-8") as f:
                parts.append(f.read())

    combined = "\n\n---\n\n".join(parts)

    with open(combined_path, "w", encoding="utf-8") as f:
        f.write(combined)
    print(f"Zapisano: {len(combined):,} znaków → {combined_path}")


# ──────────────────────────────────────────────
# Tryb STANDARD — synchroniczny, plik po pliku
# ──────────────────────────────────────────────

def ocr_pdf(client: Mistral, pdf_path: Path) -> str:
    """Wyślij PDF do Mistral OCR i zwróć markdown."""
    base64_pdf = encode_pdf(pdf_path)

    response = client.ocr.process(
        model=MODEL,
        document={
            "type": "document_url",
            "document_url": f"data:application/pdf;base64,{base64_pdf}",
        },
        include_image_base64=False,
    )

    pages_text = []
    for page in response.pages:
        if page.markdown:
            pages_text.append(page.markdown)

    return "\n\n".join(pages_text)


def run_standard(args, pdf_files):
    """Przetwarzanie synchroniczne — plik po pliku."""
    client = Mistral(api_key=os.environ["MISTRAL_API_KEY"])
    cache = load_cache(args.output_dir)

    processed = 0
    skipped = 0
    errors = 0

    for idx, pdf_file in enumerate(pdf_files, 1):
        md_file = args.output_dir / f"{pdf_file.stem}.md"

        if pdf_file.name in cache and md_file.exists():
            print(f"[{idx}/{len(pdf_files)}] {pdf_file.name} — cache, pomijam")
            skipped += 1
            continue

        print(f"[{idx}/{len(pdf_files)}] {pdf_file.name} — OCR...", end=" ", flush=True)

        try:
            markdown_text = ocr_pdf(client, pdf_file)

            with open(md_file, "w", encoding="utf-8") as f:
                f.write(markdown_text)

            cache[pdf_file.name] = {
                "output": md_file.name,
                "chars": len(markdown_text),
                "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            }
            save_cache(args.output_dir, cache)

            print(f"OK ({len(markdown_text):,} znaków)")
            processed += 1

        except Exception as e:
            print(f"BŁĄD: {e}")
            errors += 1

    print(f"\n=== PODSUMOWANIE (standard) ===")
    print(f"Przetworzone: {processed}")
    print(f"Z cache:      {skipped}")
    print(f"Błędy:        {errors}")


# ──────────────────────────────────────────────
# Tryb BATCH — asynchroniczny, 50% taniej
# ──────────────────────────────────────────────

MAX_JSONL_SIZE = 400 * 1024 * 1024  # 400 MB (limit uploadu: 512 MB, zostawiamy margines)


def batch_submit(args, pdf_files):
    """Przygotuj JSONL z requestami OCR i wyślij jako batch job(s)."""
    client = Mistral(api_key=os.environ["MISTRAL_API_KEY"])
    cache = load_cache(args.output_dir)

    # Filtruj pliki, które już są w cache
    to_process = [f for f in pdf_files if f.name not in cache]
    if not to_process:
        print("Wszystkie pliki są już w cache — nic do przetworzenia.")
        return

    print(f"Przygotowuję batch: {len(to_process)} plików (pominięto {len(pdf_files) - len(to_process)} z cache)")

    # Dzielenie na partie (max ~400 MB JSONL per upload)
    batches = []
    current_batch = []
    current_size = 0

    for pdf_file in to_process:
        file_size = pdf_file.stat().st_size
        estimated_jsonl_entry = int(file_size * 1.37) + 200  # base64 overhead + JSON wrapping
        if current_size + estimated_jsonl_entry > MAX_JSONL_SIZE and current_batch:
            batches.append(current_batch)
            current_batch = []
            current_size = 0
        current_batch.append(pdf_file)
        current_size += estimated_jsonl_entry

    if current_batch:
        batches.append(current_batch)

    print(f"Podzielono na {len(batches)} partii (limit ~400 MB/partia)")

    all_jobs = []

    for batch_idx, batch_files in enumerate(batches, 1):
        print(f"\n--- Partia {batch_idx}/{len(batches)}: {len(batch_files)} plików ---")

        buffer = BytesIO()
        for pdf_file in batch_files:
            base64_pdf = encode_pdf(pdf_file)
            request = {
                "custom_id": pdf_file.name,
                "body": {
                    "model": MODEL,
                    "document": {
                        "type": "document_url",
                        "document_url": f"data:application/pdf;base64,{base64_pdf}",
                    },
                    "include_image_base64": False,
                },
            }
            buffer.write(json.dumps(request).encode("utf-8"))
            buffer.write(b"\n")
            print(f"  + {pdf_file.name}")

        jsonl_size = buffer.tell()
        print(f"  Rozmiar JSONL: {jsonl_size / 1024 / 1024:.1f} MB")

        print("  Wysyłanie...")
        buffer.seek(0)
        uploaded_file = client.files.upload(
            file={"file_name": f"ocr_batch_{batch_idx}.jsonl", "content": buffer.getvalue()},
            purpose="batch",
        )

        print("  Tworzenie batch job...")
        batch_job = client.batch.jobs.create(
            input_files=[uploaded_file.id],
            model=MODEL,
            endpoint="/v1/ocr",
            metadata={"description": f"OCR partia {batch_idx}/{len(batches)}"},
        )

        all_jobs.append({
            "job_id": batch_job.id,
            "input_file_id": uploaded_file.id,
            "batch_index": batch_idx,
            "files": [f.name for f in batch_files],
            "total_requests": len(batch_files),
        })
        print(f"  Job ID: {batch_job.id} (status: {batch_job.status})")

    print(f"\n=== BATCH JOBS UTWORZONE: {len(all_jobs)} ===")
    for j in all_jobs:
        print(f"  Partia {j['batch_index']}: {j['job_id']} ({j['total_requests']} plików)")
    print(f"\nSprawdź postęp:  python ocr_mistral.py --batch status")
    print(f"Pobierz wyniki:  python ocr_mistral.py --batch download")

    # Zapisz stan batch (obsługa wielu jobów)
    save_batch_state(args.output_dir, {
        "jobs": all_jobs,
        "submitted_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "total_files": len(to_process),
    })


def batch_status(args):
    """Sprawdź status batch job(s)."""
    state = load_batch_state(args.output_dir)
    if not state:
        print("Brak aktywnego batch job. Najpierw uruchom: --batch submit")
        return

    client = Mistral(api_key=os.environ["MISTRAL_API_KEY"])

    # Obsługa starego formatu (jeden job) i nowego (wiele jobów)
    jobs_info = state.get("jobs", [{"job_id": state.get("job_id"), "batch_index": 1,
                                     "total_requests": state.get("total_requests", 0)}])

    print(f"=== STATUS BATCH ({len(jobs_info)} partii) ===")
    print(f"Wysłano: {state.get('submitted_at', '?')}")
    print()

    all_done = True
    for info in jobs_info:
        job = client.batch.jobs.get(job_id=info["job_id"])
        pct = 0
        if job.total_requests > 0:
            pct = (job.succeeded_requests + job.failed_requests) / job.total_requests * 100

        status_icon = {"SUCCESS": "✓", "FAILED": "✗", "RUNNING": "⟳", "QUEUED": "⏳"}.get(job.status, "?")
        print(f"  {status_icon} Partia {info.get('batch_index', '?')}: {job.status}"
              f"  [{job.succeeded_requests}/{job.total_requests} OK, {job.failed_requests} err, {pct:.0f}%]")

        if job.status not in ("SUCCESS", "FAILED"):
            all_done = False

    if all_done:
        print(f"\nWszystkie partie gotowe! Pobierz: python ocr_mistral.py --batch download")
    else:
        print(f"\nCzekaj — przetwarzanie w toku...")


def _download_job_results(client, job, output_dir: Path, cache: dict) -> tuple[int, int]:
    """Pobierz wyniki jednego batch job. Zwraca (saved, errors)."""
    if not job.output_file:
        print(f"  Brak pliku wyjściowego.")
        return 0, 0

    output = client.files.download(file_id=job.output_file)
    content = b""
    for chunk in output.stream:
        content += chunk
    results_text = content.decode("utf-8")

    saved = 0
    errors = 0

    for line in results_text.strip().split("\n"):
        if not line.strip():
            continue

        result = json.loads(line)
        custom_id = result.get("custom_id", "")
        response_body = result.get("response", {}).get("body", {})

        pages = response_body.get("pages", [])
        pages_text = []
        for page in pages:
            md = page.get("markdown", "")
            if md:
                pages_text.append(md)

        if not pages_text:
            error = result.get("error")
            print(f"  {custom_id} — brak tekstu (error: {error})")
            errors += 1
            continue

        markdown_text = "\n\n".join(pages_text)
        stem = Path(custom_id).stem
        md_file = output_dir / f"{stem}.md"

        with open(md_file, "w", encoding="utf-8") as f:
            f.write(markdown_text)

        cache[custom_id] = {
            "output": md_file.name,
            "chars": len(markdown_text),
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "source": "batch",
        }
        saved += 1
        print(f"  {custom_id} → {md_file.name} ({len(markdown_text):,} znaków)")

    # Pobierz error file jeśli istnieje
    if job.error_file:
        err_output = client.files.download(file_id=job.error_file)
        err_content = b""
        for chunk in err_output.stream:
            err_content += chunk
        err_path = output_dir / f"_batch_errors_{job.id[:8]}.jsonl"
        with open(err_path, "wb") as f:
            f.write(err_content)
        print(f"  Plik błędów: {err_path}")

    return saved, errors


def batch_download(args, pdf_files):
    """Pobierz wyniki batch job(s) i zapisz jako pliki .md."""
    state = load_batch_state(args.output_dir)
    if not state:
        print("Brak aktywnego batch job. Najpierw uruchom: --batch submit")
        return

    client = Mistral(api_key=os.environ["MISTRAL_API_KEY"])

    # Obsługa starego formatu (jeden job) i nowego (wiele jobów)
    jobs_info = state.get("jobs", [{"job_id": state.get("job_id"), "batch_index": 1}])

    cache = load_cache(args.output_dir)
    total_saved = 0
    total_errors = 0

    for info in jobs_info:
        job = client.batch.jobs.get(job_id=info["job_id"])
        batch_idx = info.get("batch_index", "?")

        if job.status != "SUCCESS":
            print(f"Partia {batch_idx}: nie gotowa (status: {job.status}) — pomijam")
            continue

        print(f"\nPartia {batch_idx}: pobieranie wyników...")
        saved, errors = _download_job_results(client, job, args.output_dir, cache)
        total_saved += saved
        total_errors += errors

    save_cache(args.output_dir, cache)

    print(f"\n=== PODSUMOWANIE (batch download) ===")
    print(f"Zapisanych: {total_saved}")
    print(f"Błędów:     {total_errors}")


# ──────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="OCR zeskanowanych książek (PDF) za pomocą Mistral OCR API",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Przykłady:
  # Podgląd
  python backend/test_code/ocr_mistral.py --input-dir "H:\\Mój dysk\\ksiazki\\moja_ksiazka" --dry-run

  # Tryb standardowy ($2/1000 stron)
  python backend/test_code/ocr_mistral.py --input-dir ./pdfs --combine

  # Tryb batch ($1/1000 stron, 50% taniej)
  python backend/test_code/ocr_mistral.py --input-dir ./pdfs --batch submit
  python backend/test_code/ocr_mistral.py --input-dir ./pdfs --batch status
  python backend/test_code/ocr_mistral.py --input-dir ./pdfs --batch download --combine

  # Wynik zapisywany domyślnie w {input-dir}/markdown_ocr/
  # Można zmienić: --output-dir "D:\\wyniki"
        """,
    )
    parser.add_argument("--input-dir", type=Path, required=True,
                        help="Katalog z plikami PDF (wymagany)")
    parser.add_argument("--output-dir", type=Path, default=None,
                        help="Katalog wyjściowy (domyślnie: {input-dir}/markdown_ocr)")
    parser.add_argument("--pattern", type=str, default="IMG_*.pdf",
                        help="Wzorzec nazw plików PDF (domyślnie: IMG_*.pdf)")
    parser.add_argument("--combine", action="store_true",
                        help="Połącz wyniki w jeden plik _cala_ksiazka.md")
    parser.add_argument("--batch", type=str, choices=["submit", "status", "download"],
                        help="Tryb batch: submit / status / download")
    parser.add_argument("--dry-run", action="store_true",
                        help="Pokaż plan bez wysyłania do API")
    args = parser.parse_args()

    # Domyślny output-dir = {input-dir}/markdown_ocr
    if args.output_dir is None:
        args.output_dir = args.input_dir / "markdown_ocr"

    # Walidacja klucza API
    api_key = os.environ.get("MISTRAL_API_KEY")
    if not api_key and not args.dry_run:
        print("BŁĄD: Ustaw zmienną MISTRAL_API_KEY")
        print("  export MISTRAL_API_KEY='your-key'")
        print("  Klucz uzyskasz na: https://console.mistral.ai/api-keys")
        sys.exit(1)

    pdf_files = get_pdf_files(args.input_dir, args.pattern)
    if not pdf_files and args.batch != "status":
        print(f"Nie znaleziono plików '{args.pattern}' w {args.input_dir}")
        sys.exit(1)

    args.output_dir.mkdir(parents=True, exist_ok=True)

    # Dry run
    if args.dry_run:
        cache = load_cache(args.output_dir)
        cached = sum(1 for f in pdf_files if f.name in cache)
        total_size = sum(f.stat().st_size for f in pdf_files)
        est_pages = len(pdf_files) * 2  # szacunek: ~2 strony/PDF

        print(f"=== PLAN OCR ===")
        print(f"Plików PDF:     {len(pdf_files)}")
        print(f"Rozmiar łączny: {total_size / 1024 / 1024:.1f} MB")
        print(f"Szac. stron:    ~{est_pages}")
        print(f"Z cache:        {cached}")
        print(f"Do przetworzenia: {len(pdf_files) - cached}")
        print(f"")
        print(f"Szacunkowy koszt:")
        print(f"  Standard: ~${est_pages * 0.002:.2f} ($2/1000 stron)")
        print(f"  Batch:    ~${est_pages * 0.001:.2f} ($1/1000 stron)")
        print()
        for f in pdf_files:
            status = "✓ cache" if f.name in cache else "  nowy"
            size_kb = f.stat().st_size / 1024
            print(f"  {status}  {f.name}  ({size_kb:.0f} KB)")
        return

    # Batch mode
    if args.batch == "submit":
        batch_submit(args, pdf_files)
    elif args.batch == "status":
        batch_status(args)
    elif args.batch == "download":
        batch_download(args, pdf_files)
        if args.combine:
            combine_markdown(pdf_files, args.output_dir)
    else:
        # Standard mode
        run_standard(args, pdf_files)
        if args.combine:
            combine_markdown(pdf_files, args.output_dir)


if __name__ == "__main__":
    main()
