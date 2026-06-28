#!/usr/bin/env python3
"""
Skrypt porównujący odpowiedzi różnych modeli AI na pytanie o ich tożsamość.
Każdy model jest pytany ITERATIONS razy o: "jak się nazywasz i kto Cię stworzył?"

Wspierane providery: OpenRouter (modele zachodnie + chińskie), AWS Bedrock,
OpenAI (bezpośrednio), CloudFerro Sherlock (Bielik).

Uruchamianie (z katalogu backend/):
    python test_code/model_identity_comparison.py
    python test_code/model_identity_comparison.py --iterations 10
    python test_code/model_identity_comparison.py --only openrouter
    python test_code/model_identity_comparison.py --list-models
"""

import argparse
import csv
import json
import logging
import os
import sys
import time
from collections import Counter
from datetime import datetime
from pathlib import Path

import boto3
from dotenv import load_dotenv
from openai import OpenAI

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Konfiguracja
# ---------------------------------------------------------------------------

script_dir = Path(__file__).parent


def _find_env_file(start: Path) -> str | None:
    """Szuka pliku .env idąc w górę drzewa katalogów od start."""
    current = start.resolve()
    while True:
        candidate = current / ".env"
        if candidate.exists():
            return str(candidate)
        parent = current.parent
        if parent == current:
            return None
        current = parent


def _load_config_with_vault_fallback(start_dir: Path) -> None:
    """Ładuje konfigurację z Vault (jeśli dostępny) z fallbackiem do .env.

    Kolejność:
    1. Szuka .env idąc w górę drzewa katalogów od start_dir (find_dotenv).
    2. Jeśli SECRETS_BACKEND=vault i dane dostępowe są obecne — pobierz sekrety z Vault
       i wstrzyknij do os.environ.
    3. W razie błędu Vault — zostań przy wartościach z .env i wyświetl ostrzeżenie.
    """
    dotenv_path = _find_env_file(start_dir) or str(start_dir / ".env")
    load_dotenv(dotenv_path)
    print(f"Konfiguracja: wczytano .env z {dotenv_path}")

    secrets_backend = os.environ.get("SECRETS_BACKEND", "env")
    if secrets_backend != "vault":
        print("Konfiguracja: backend=env (.env).")
        return

    vault_addr = os.environ.get("VAULT_ADDR")
    vault_token = os.environ.get("VAULT_TOKEN")
    if not vault_addr or not vault_token:
        print("UWAGA: SECRETS_BACKEND=vault, ale brak VAULT_ADDR/VAULT_TOKEN — używam .env.")
        return

    try:
        import hvac  # noqa: PLC0415

        project_code = os.environ.get("PROJECT_CODE", "lenie")
        secrets_env = os.environ.get("SECRETS_ENV") or os.environ.get("VAULT_ENV", "dev")
        secret_path = f"{project_code}/{secrets_env}"

        client = hvac.Client(url=vault_addr, token=vault_token)
        if not client.is_authenticated():
            print("UWAGA: Vault — błąd uwierzytelnienia — używam .env jako fallback.")
            return

        response = client.secrets.kv.v2.read_secret_version(
            path=secret_path,
            mount_point="secret",
        )
        vault_data = response["data"]["data"]
        for key, value in vault_data.items():
            if isinstance(value, str):
                os.environ[key] = value
        print(f"Konfiguracja załadowana z Vault ({vault_addr}, ścieżka: secret/{secret_path}).")
    except ImportError:
        print("UWAGA: Brak pakietu hvac — używam .env jako fallback. Zainstaluj: uv add hvac")
    except Exception as exc:  # noqa: BLE001
        print(f"UWAGA: Vault niedostępny ({exc}) — używam .env jako fallback.")


_load_config_with_vault_fallback(script_dir)

QUESTION = "jak się nazywasz i kto Cię stworzył? Odpowiedz jednym zdaniem"
DEFAULT_ITERATIONS = 100
DELAY_BETWEEN_CALLS = 0.3  # sekundy między wywołaniami (ostrożność rate-limit)
MAX_TOKENS = 400

# ---------------------------------------------------------------------------
# Lista modeli do testowania
# Możesz odkomentować/zakomentować poszczególne modele lub dodać nowe.
# ---------------------------------------------------------------------------

MODELS_TO_TEST = [
    # ------------------------------------------------------------------
    # OpenRouter — modele zachodnie
    # ------------------------------------------------------------------
    {
        "provider": "openrouter",
        "model_id": "anthropic/claude-3-haiku",
        "display_name": "Claude 3 Haiku (Anthropic) via OpenRouter",
        "tags": ["western"],
    },
    {
        "provider": "openrouter",
        "model_id": "openai/gpt-4o-mini",
        "display_name": "GPT-4o Mini (OpenAI) via OpenRouter",
        "tags": ["western"],
    },
    {
        "provider": "openrouter",
        "model_id": "meta-llama/llama-3.1-8b-instruct",
        "display_name": "Llama 3.1 8B (Meta) via OpenRouter",
        "tags": ["western"],
    },
    {
        "provider": "openrouter",
        "model_id": "google/gemini-flash-1.5-8b",
        "display_name": "Gemini Flash 1.5 8B (Google) via OpenRouter",
        "tags": ["western"],
    },
    # ------------------------------------------------------------------
    # OpenRouter — modele chińskie
    # ------------------------------------------------------------------
    {
        "provider": "openrouter",
        "model_id": "deepseek/deepseek-chat",
        "display_name": "DeepSeek Chat (DeepSeek, Chiny) via OpenRouter",
        "tags": ["chinese"],
    },
    {
        "provider": "openrouter",
        "model_id": "deepseek/deepseek-r1",
        "display_name": "DeepSeek R1 (DeepSeek, Chiny) via OpenRouter",
        "tags": ["chinese"],
    },
    {
        "provider": "openrouter",
        "model_id": "qwen/qwen-2.5-72b-instruct",
        "display_name": "Qwen 2.5 72B (Alibaba, Chiny) via OpenRouter",
        "tags": ["chinese"],
    },
    {
        "provider": "openrouter",
        "model_id": "01-ai/yi-large",
        "display_name": "Yi Large (01.AI, Chiny) via OpenRouter",
        "tags": ["chinese"],
    },
    {
        "provider": "openrouter",
        "model_id": "minimax/minimax-01",
        "display_name": "MiniMax-01 (MiniMax, Chiny) via OpenRouter",
        "tags": ["chinese"],
    },
    # ------------------------------------------------------------------
    # AWS Bedrock
    # ------------------------------------------------------------------
    {
        "provider": "bedrock",
        "model_id": "anthropic.claude-3-haiku-20240307-v1:0",
        "display_name": "Claude 3 Haiku via AWS Bedrock",
        "tags": ["bedrock", "western"],
    },
    {
        "provider": "bedrock",
        "model_id": "amazon.nova-lite-v1:0",
        "display_name": "Amazon Nova Lite via AWS Bedrock",
        "tags": ["bedrock", "western"],
    },
    {
        "provider": "bedrock",
        "model_id": "meta.llama3-8b-instruct-v1:0",
        "display_name": "Llama 3 8B via AWS Bedrock",
        "tags": ["bedrock", "western"],
    },
    # ------------------------------------------------------------------
    # OpenAI — bezpośrednio (bez OpenRouter)
    # ------------------------------------------------------------------
    {
        "provider": "openai",
        "model_id": "gpt-4o-mini",
        "display_name": "GPT-4o Mini (OpenAI bezpośrednio)",
        "tags": ["western"],
    },
    # ------------------------------------------------------------------
    # CloudFerro Sherlock — Bielik (polski model)
    # ------------------------------------------------------------------
    {
        "provider": "cloudferro",
        "model_id": "Bielik-11B-v2.3-Instruct",
        "display_name": "Bielik 11B v2.3 (CloudFerro Sherlock)",
        "tags": ["polish"],
    },
]


# ---------------------------------------------------------------------------
# Inicjalizacja klientów
# ---------------------------------------------------------------------------

def create_clients() -> dict:
    """Tworzy klientów API dla każdego dostępnego providera."""
    clients = {}

    openrouter_key = os.environ.get("OPENROUTER_API_KEY")
    if openrouter_key:
        clients["openrouter"] = OpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=openrouter_key,
        )
    else:
        print("UWAGA: OPENROUTER_API_KEY nie znaleziony — modele OpenRouter pominięte.")

    openai_key = os.environ.get("OPENAI_API_KEY")
    if openai_key:
        clients["openai"] = OpenAI(api_key=openai_key)
    else:
        print("UWAGA: OPENAI_API_KEY nie znaleziony — OpenAI pominięty.")

    cloudferro_key = os.environ.get("CLOUDFERRO_SHERLOCK_KEY")
    if cloudferro_key:
        clients["cloudferro"] = OpenAI(
            api_key=cloudferro_key,
            base_url="https://api-sherlock.cloudferro.com/openai/v1",
        )
    else:
        print("UWAGA: CLOUDFERRO_SHERLOCK_KEY nie znaleziony — CloudFerro pominięty.")

    aws_access_key = os.environ.get("AWS_ACCESS_KEY_ID")
    aws_secret_key = os.environ.get("AWS_SECRET_ACCESS_KEY")
    aws_region = os.environ.get("AWS_REGION", "eu-central-1")
    if aws_access_key and aws_secret_key:
        clients["bedrock"] = boto3.client(
            "bedrock-runtime",
            aws_access_key_id=aws_access_key,
            aws_secret_access_key=aws_secret_key,
            region_name=aws_region,
        )
    else:
        print("UWAGA: AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY nie znalezione — Bedrock pominięty.")

    return clients


# ---------------------------------------------------------------------------
# Wywołania API
# ---------------------------------------------------------------------------

def ask_openai_compatible(client: OpenAI, model_id: str, question: str) -> str:
    """Pytanie przez API kompatybilne z OpenAI (OpenRouter, OpenAI, CloudFerro)."""
    response = client.chat.completions.create(
        model=model_id,
        messages=[{"role": "user", "content": question}],
        max_tokens=MAX_TOKENS,
        temperature=0.7,
    )
    return response.choices[0].message.content.strip()


def ask_bedrock(client, model_id: str, question: str) -> str:
    """Pytanie przez AWS Bedrock Converse API."""
    response = client.converse(
        modelId=model_id,
        messages=[{
            "role": "user",
            "content": [{"text": question}],
        }],
        inferenceConfig={
            "maxTokens": MAX_TOKENS,
            "temperature": 0.7,
        },
    )
    return response["output"]["message"]["content"][0]["text"].strip()


# ---------------------------------------------------------------------------
# Testowanie modelu
# ---------------------------------------------------------------------------

def _is_fatal_error(exc: Exception) -> bool:
    """Zwraca True dla błędów, które nie ustąpią przy ponownych próbach.

    Fatalne: 401 (autoryzacja), 403 (brak dostępu), 404 (nieznany model).
    Niefatalne: 429 (rate limit), 500/502/503 (przejściowe błędy serwera).
    """
    msg = str(exc)
    for code in ("401", "403", "404"):
        if f"code: {code}" in msg or f"'code': {code}" in msg or f'"code": {code}' in msg:
            return True
    return False


def test_model(
    model_config: dict,
    clients: dict,
    iterations: int,
    delay: float,
) -> dict:
    """Testuje jeden model iterations razy i zwraca zebrane odpowiedzi."""
    provider = model_config["provider"]
    model_id = model_config["model_id"]
    display_name = model_config["display_name"]

    print(f"\n{'='*65}")
    print(f"  Model  : {display_name}")
    print(f"  ID     : {model_id}")
    print(f"  Pytania: {iterations}")
    print(f"{'='*65}")

    responses: list[str] = []
    errors: list[dict] = []

    for i in range(1, iterations + 1):
        try:
            if provider in ("openrouter", "openai", "cloudferro"):
                answer = ask_openai_compatible(clients[provider], model_id, QUESTION)
            elif provider == "bedrock":
                answer = ask_bedrock(clients["bedrock"], model_id, QUESTION)
            else:
                raise ValueError(f"Nieznany provider: {provider}")

            responses.append(answer)

            if i % 10 == 0:
                unique_so_far = len(set(responses))
                print(f"  [{i:3d}/{iterations}] OK  (unikalnych odpowiedzi do tej pory: {unique_so_far})")

        except KeyboardInterrupt:
            print("\n  Przerwano przez użytkownika.")
            break
        except Exception as exc:
            error_msg = str(exc)
            errors.append({"iteration": i, "error": error_msg})
            print(f"  [{i:3d}/{iterations}] BŁĄD: {error_msg[:120]}")
            if _is_fatal_error(exc):
                print("  Błąd fatalny (autoryzacja/nieznany model) — przerywam ten model.")
                break

        if delay > 0 and i < iterations:
            time.sleep(delay)

    return {
        "model_config": model_config,
        "responses": responses,
        "errors": errors,
        "total_calls": iterations,
        "successful_calls": len(responses),
        "failed_calls": len(errors),
    }


# ---------------------------------------------------------------------------
# Analiza wyników
# ---------------------------------------------------------------------------

def analyze_results(all_results: list[dict]) -> None:
    """Wyświetla podsumowanie wyników dla wszystkich modeli."""
    print(f"\n{'#'*65}")
    print("  PODSUMOWANIE PORÓWNANIA MODELI")
    print(f"  Pytanie: \"{QUESTION}\"")
    print(f"{'#'*65}")

    for result in all_results:
        config = result["model_config"]
        responses = result["responses"]

        print(f"\n{'─'*65}")
        print(f"  {config['display_name']}")
        print(
            f"  Udane: {result['successful_calls']}/{result['total_calls']}"
            f"  |  Błędy: {result['failed_calls']}"
        )

        if not responses:
            print("  Brak odpowiedzi — wszystkie wywołania zakończyły się błędem.")
            continue

        counter = Counter(responses)
        unique_count = len(counter)
        print(f"  Unikalnych odpowiedzi: {unique_count} / {len(responses)}")

        print("\n  Top 5 najczęstszych odpowiedzi:")
        for rank, (response, count) in enumerate(counter.most_common(5), 1):
            percentage = count / len(responses) * 100
            # Pierwsza linia odpowiedzi jako podgląd
            first_line = response.split("\n")[0][:120]
            suffix = "..." if len(response) > 120 or "\n" in response else ""
            print(f"    {rank}. [{count:3d}x = {percentage:5.1f}%] {first_line}{suffix}")

        if result["errors"]:
            print(f"\n  Przykładowe błędy (max 3):")
            for err in result["errors"][:3]:
                print(f"    iter {err['iteration']}: {err['error'][:100]}")


# ---------------------------------------------------------------------------
# Zapis wyników
# ---------------------------------------------------------------------------

def save_results(all_results: list[dict], output_dir: Path) -> None:
    """Zapisuje wyniki do pliku JSON i CSV."""
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    # --- JSON (pełne odpowiedzi) ---
    json_path = output_dir / f"model_comparison_{timestamp}.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(all_results, f, ensure_ascii=False, indent=2)
    print(f"\n  Pełne wyniki (JSON): {json_path}")

    # --- CSV (każda odpowiedź jako wiersz) ---
    csv_path = output_dir / f"model_comparison_{timestamp}.csv"
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["model_display", "provider", "model_id", "iteration", "response", "error"])
        for result in all_results:
            config = result["model_config"]
            for idx, response in enumerate(result["responses"], 1):
                writer.writerow([
                    config["display_name"],
                    config["provider"],
                    config["model_id"],
                    idx,
                    response,
                    "",
                ])
            for err in result["errors"]:
                writer.writerow([
                    config["display_name"],
                    config["provider"],
                    config["model_id"],
                    err["iteration"],
                    "",
                    err["error"],
                ])
    print(f"  Wyniki wiersz-po-wierszu (CSV): {csv_path}")

    # --- Plik podsumowania (tekstowy) ---
    summary_path = output_dir / f"model_comparison_{timestamp}_summary.txt"
    with open(summary_path, "w", encoding="utf-8") as f:
        f.write(f"Porównanie modeli AI — pytanie o tożsamość\n")
        f.write(f"Pytanie: {QUESTION}\n")
        f.write(f"Data: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
        for result in all_results:
            config = result["model_config"]
            responses = result["responses"]
            f.write(f"{'='*60}\n")
            f.write(f"Model: {config['display_name']}\n")
            f.write(f"Provider: {config['provider']} | ID: {config['model_id']}\n")
            f.write(
                f"Udane: {result['successful_calls']}/{result['total_calls']} | "
                f"Błędy: {result['failed_calls']}\n"
            )
            if responses:
                counter = Counter(responses)
                f.write(f"Unikalnych odpowiedzi: {len(counter)}\n\n")
                f.write("Top 5 najczęstszych odpowiedzi:\n")
                for rank, (resp, cnt) in enumerate(counter.most_common(5), 1):
                    pct = cnt / len(responses) * 100
                    f.write(f"  {rank}. [{cnt}x / {pct:.1f}%]\n{resp}\n\n")
            else:
                f.write("Brak odpowiedzi.\n")
    print(f"  Podsumowanie (TXT):  {summary_path}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args():
    parser = argparse.ArgumentParser(
        description="Porównanie modeli AI — pytanie o tożsamość"
    )
    parser.add_argument(
        "--iterations", "-n",
        type=int,
        default=DEFAULT_ITERATIONS,
        help=f"Liczba pytań per model (domyślnie: {DEFAULT_ITERATIONS})",
    )
    parser.add_argument(
        "--only",
        choices=["openrouter", "openai", "bedrock", "cloudferro", "chinese", "western", "polish"],
        help="Ogranicz testy do wybranego providera lub tagu",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=DELAY_BETWEEN_CALLS,
        help=f"Opóźnienie między wywołaniami w sekundach (domyślnie: {DELAY_BETWEEN_CALLS})",
    )
    parser.add_argument(
        "--list-models",
        action="store_true",
        help="Wyświetl listę skonfigurowanych modeli i zakończ",
    )
    parser.add_argument(
        "--question", "-q",
        type=str,
        default=QUESTION,
        help=f"Pytanie do zadania modelom (domyślnie: \"{QUESTION}\")",
    )
    return parser.parse_args()


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def main():
    args = parse_args()

    question = args.question

    # Wyświetl listę modeli i zakończ
    if args.list_models:
        print(f"Skonfigurowane modele ({len(MODELS_TO_TEST)}):\n")
        for i, m in enumerate(MODELS_TO_TEST, 1):
            tags = ", ".join(m.get("tags", []))
            print(f"  {i:2d}. [{m['provider']:12s}] {m['display_name']}")
            if tags:
                print(f"       tagi: {tags}")
        return

    # Filtrowanie modeli
    models = MODELS_TO_TEST
    if args.only:
        if args.only in ("openrouter", "openai", "bedrock", "cloudferro"):
            models = [m for m in models if m["provider"] == args.only]
        else:
            models = [m for m in models if args.only in m.get("tags", [])]
        if not models:
            print(f"Brak modeli pasujących do filtru: {args.only}")
            sys.exit(1)

    print(f"\n{'='*65}")
    print(f"  Model Identity Comparison")
    print(f"  Pytanie : \"{question}\"")
    print(f"  Iteracje: {args.iterations} per model")
    print(f"  Modeli  : {len(models)}")
    print(f"  Opóźnienie: {args.delay}s")
    print(f"{'='*65}")

    # Inicjalizacja klientów
    clients = create_clients()

    # Filtruj modele do tych, dla których mamy klienta
    runnable = [m for m in models if m["provider"] in clients]
    skipped = [m for m in models if m["provider"] not in clients]

    if skipped:
        print(f"\nPominięte (brak klienta):")
        for m in skipped:
            print(f"  - {m['display_name']}")

    if not runnable:
        print("\nBrak modeli do uruchomienia. Sprawdź zmienne środowiskowe w .env.")
        sys.exit(1)

    # Uruchom testy
    all_results = []
    start_total = time.time()

    for model_config in runnable:
        start = time.time()
        result = test_model(model_config, clients, args.iterations, args.delay)
        elapsed = time.time() - start
        print(f"  Czas: {elapsed:.1f}s")
        all_results.append(result)

    total_elapsed = time.time() - start_total
    print(f"\n  Łączny czas wykonania: {total_elapsed:.1f}s")

    # Pokaż podsumowanie
    analyze_results(all_results)

    # Zapisz wyniki
    output_dir = script_dir / "tmp"
    save_results(all_results, output_dir)


if __name__ == "__main__":
    main()
