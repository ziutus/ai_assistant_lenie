"""Compare entity-sense providers independently, without writing audit/usage rows.

Run from backend with PYTHONPATH=.; remote calls require explicit CLI execution.
The fixture tests semantic understanding, including words excluded by the narrow
production candidate filter. No fallback is used for an individual provider.
"""

from __future__ import annotations

import argparse
import json
import math
import time
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch

from library.entity_sense_classifier import (
    DEFAULT_DECISION_MODELS,
    SENSES,
    SenseProvider,
    _config,
    _daily_calls,
    _enabled,
    candidate_country,
    fallback_models,
)

DEFAULT_FIXTURE = Path(__file__).parents[1] / "tests" / "fixtures" / "entity_sense_cases.json"


def provider_names(config):
    models = str(config.get("ENTITY_SENSE_DECISION_MODELS", DEFAULT_DECISION_MODELS) or "").split(",")
    return (["fabryka"] + [f"decisions:{model.strip()}" for model in models if model.strip()]
            + [f"llm:{model}" for model in fallback_models(config)[:1]])


def normalize_provider(name):
    return "openrouter/" + name.removeprefix("openrouter:") if name.startswith("openrouter:") else name


def evaluate(cases, providers, config, max_basal_calls=8):
    engine = SenseProvider()
    providers = list(dict.fromkeys(normalize_provider(name) for name in providers))
    budget = 0
    if "fabryka" in providers and config.get("FABRYKA_API_KEY"):
        used = _daily_calls()
        try:
            limit = int(config.get("FABRYKA_DAILY_LIMIT", 10))
            budget = min(max(0, max_basal_calls), max(0, limit - used)) if used is not None else 0
        except (TypeError, ValueError):
            pass
    report = {}
    # Existing clients record usage unconditionally. Suppress only their write
    # boundaries in this standalone, sequential CLI; quota reads remain active.
    with ExitStack() as stack:
        stack.enter_context(patch("library.external_service_events.record_external_service_event"))
        stack.enter_context(patch("library.ai._record_usage"))
        for provider in providers:
            rows = []
            matrix = {actual: {predicted: 0 for predicted in (*SENSES, "brak")} for actual in SENSES}
            for case in cases:
                started = time.perf_counter()
                result, error = None, None
                candidate = {"entity_text": case["word"], "country": candidate_country([case["word"]])}
                try:
                    if provider == "fabryka":
                        if budget > 0:
                            budget -= 1
                            result = engine.basal(candidate, case["context"], "Ewaluacja", None, config)
                        if result is None:
                            error = "Basal unavailable or quota exhausted/unknown"
                    elif provider.startswith("decisions:"):
                        result = engine.decisions(provider.removeprefix("decisions:"), candidate, case["context"],
                                                  "Ewaluacja", None, config)
                        if result is None:
                            error = "Decisions unavailable, disabled, unconfigured or circuit open"
                    elif provider.removeprefix("llm:").startswith("openrouter/") and not _enabled(config.get("OPENROUTER_ENABLED", False)):
                        error = "OpenRouter disabled"
                    else:
                        result = engine.llm(provider.removeprefix("llm:"), candidate, case["context"], "Ewaluacja", None)
                except (Exception, SystemExit) as exc:
                    error = f"{type(exc).__name__}: {exc}"
                predicted = result["sense"] if result else "brak"
                matrix[case["expected"]][predicted] += 1
                rows.append({**case, "result": result, "error": error,
                             "correct": predicted == case["expected"], "seconds": time.perf_counter() - started})
            count = len(rows)
            missing = sum(row["result"] is None for row in rows)
            correct = sum(row["correct"] for row in rows)
            report[provider] = {
                "cases": count, "correct": correct, "accuracy": correct / count if count else 0,
                "errors": count - correct - missing, "no_answer": missing,
                "mean_seconds": sum(row["seconds"] for row in rows) / count if count else 0,
                "total_cost_usd": sum(_reported_cost(row["result"]) for row in rows),
                "confusion_matrix": matrix, "results": rows,
            }
    return report


def _reported_cost(result):
    usage = result.get("usage") if result else None
    cost = usage.get("cost") if isinstance(usage, dict) else None
    return cost if (isinstance(cost, (int, float)) and not isinstance(cost, bool)
                    and math.isfinite(cost) and cost >= 0) else 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixture", type=Path, default=DEFAULT_FIXTURE)
    parser.add_argument("--providers", help="Comma-separated fabryka,decisions:<model>,llm:<model>")
    parser.add_argument("--max-basal-calls", type=int, default=8)
    parser.add_argument("--json", action="store_true", help="Print the complete JSON report")
    args = parser.parse_args(argv)
    config = _config()
    providers = [name.strip() for name in args.providers.split(",") if name.strip()] if args.providers else provider_names(config)
    cases = json.loads(args.fixture.read_text(encoding="utf-8"))
    report = evaluate(cases, providers, config, args.max_basal_calls)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print("Provider | accuracy | błędy | brak odpowiedzi | średni czas (s) | raportowany koszt (USD)")
        for provider, result in report.items():
            print(f"{provider} | {result['accuracy']:.1%} | {result['errors']} | "
                  f"{result['no_answer']} | {result['mean_seconds']:.3f} | {result['total_cost_usd']:.8f}")
            print("Macierz: oczekiwane -> przewidziane " + ", ".join((*SENSES, "brak")))
            for expected, counts in result["confusion_matrix"].items():
                print(f"  {expected}: " + ", ".join(str(value) for value in counts.values()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
