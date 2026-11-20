"""Evaluate the one-word person classifier on tests/fixtures/person_context_cases.json.

Runs the REAL model (default: NER_CONTEXT_MODEL, i.e. Bielik) in batches exactly like production and
compares each verdict with the expected class. A candidate counts as "dropped" when the model answers
not_person with high confidence, which is what removes the entity in production.

    cd backend
    PYTHONPATH=. python imports/evaluate_person_context.py [--model M] [--prompt-file F] [--repeat N]

--prompt-file replaces the system prompt (to compare wordings), --repeat runs the whole set N times.
Each call writes usage rows (operation ner_person_context_verification, no document id).
"""

from __future__ import annotations

import argparse
import json
import random
from collections import Counter
from pathlib import Path

from library import person_context_classifier as classifier

FIXTURE = Path(__file__).resolve().parent.parent / "tests" / "fixtures" / "person_context_cases.json"


def load_cases(path: Path = FIXTURE) -> tuple[str, list[dict]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    return data.get("title", ""), data["cases"]


def run_once(title: str, cases: list[dict], model: str, single_pass: bool = False) -> list[dict]:
    """One pass over every case; returns the cases with `predicted`, `confidence`, `dropped`, `rationale`."""
    candidates = [{"entity_text": case["candidate"], "context": case["context"]} for case in cases]
    if single_pass:
        answers = classifier._classify_all(candidates, title, None, model)
    else:
        answers = classifier.classify_candidates(candidates, title, None, model)
    by_text = {answer["entity_text"]: answer for answer in answers}
    results = []
    for case in cases:
        answer = by_text.get(case["candidate"])
        results.append({
            **case,
            "predicted": answer["predicted_class"] if answer else "missing",
            "confidence": answer["confidence"] if answer else "",
            "dropped": bool(answer and answer["dropped"]),
            "rationale": answer["rationale"] if answer else "",
        })
    return results


def score(results: list[dict]) -> dict:
    """`harmful` = a real person that would be removed; `missed` = a non-person that would stay."""
    harmful = [r for r in results if r["expected"] == "person" and r["dropped"]]
    missed = [r for r in results if r["expected"] == "not_person" and not r["dropped"]]
    return {
        "total": len(results),
        "harmful_drops": len(harmful),
        "missed_drops": len(missed),
        "missing": sum(1 for r in results if r["predicted"] == "missing"),
        "confusion": dict(Counter((r["expected"], r["predicted"], r["confidence"]) for r in results)),
        "harmful": [r["candidate"] for r in harmful],
        "missed": [r["candidate"] for r in missed],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--model", default=None, help="model id (default: NER_CONTEXT_MODEL / Bielik)")
    parser.add_argument("--prompt-file", default=None, help="file with an alternative system prompt")
    parser.add_argument("--repeat", type=int, default=1)
    parser.add_argument("--single-pass", action="store_true", help="skip the confirming second pass")
    parser.add_argument("--shuffle", action="store_true",
                        help="a different batch composition on every run (a verdict depends on the neighbours)")
    parser.add_argument("--verbose", action="store_true", help="print every wrong verdict with its rationale")
    args = parser.parse_args()

    if args.prompt_file:
        classifier._SYSTEM_PROMPT = Path(args.prompt_file).read_text(encoding="utf-8").strip()
    model = args.model or classifier._model()
    title, cases = load_cases()
    print(f"model={model} cases={len(cases)} batch={classifier.MAX_CANDIDATES_PER_CALL} repeat={args.repeat}")
    for run in range(1, args.repeat + 1):
        order = random.Random(run).sample(cases, len(cases)) if args.shuffle else cases
        results = run_once(title, order, model, single_pass=args.single_pass)
        summary = score(results)
        print(f"run {run}: harmful_drops={summary['harmful_drops']} missed_drops={summary['missed_drops']} "
              f"missing={summary['missing']} of {summary['total']}")
        print("   harmful:", summary["harmful"])
        print("   missed: ", summary["missed"])
        if args.verbose:
            for r in results:
                wrong = (r["expected"] == "person" and r["dropped"]) or (r["expected"] == "not_person" and not r["dropped"])
                if wrong:
                    print(f"   - {r['candidate']}: {r['predicted']}/{r['confidence']} :: {r['rationale']}")


if __name__ == "__main__":
    main()
