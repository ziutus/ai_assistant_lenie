"""Run the stage-10 search parser fixture against the configured real model."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from sqlalchemy import delete

from library.db.engine import get_session
from library.db.models import LlmUsageLog, SearchInterpretationLog
from library.search.evaluation import score_case, summarize
from library.search.parser import parse_search_query

DEFAULT_FIXTURE = Path(__file__).parents[1] / "tests" / "fixtures" / "search_query_cases.json"


def cleanup_evaluation_rows(results: list[dict]) -> None:
    """Remove only audit/usage rows whose exact IDs were returned by this run."""
    usage_ids = [item["usage_log_id"] for item in results if item["usage_log_id"] is not None]
    interpretation_ids = [item["interpretation_log_id"] for item in results if item["interpretation_log_id"] is not None]
    session = get_session()
    try:
        if usage_ids:
            session.execute(delete(LlmUsageLog).where(LlmUsageLog.id.in_(usage_ids)))
        if interpretation_ids:
            session.execute(delete(SearchInterpretationLog).where(SearchInterpretationLog.id.in_(interpretation_ids)))
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixture", type=Path, default=DEFAULT_FIXTURE)
    parser.add_argument("--output", type=Path, required=True, help="JSON report path")
    parser.add_argument("--model", help="Override SEARCH_QUERY_PARSER_MODEL")
    parser.add_argument("--keep-audit", action="store_true", help="Keep generated NAS audit/usage rows")
    args = parser.parse_args()

    fixture = json.loads(args.fixture.read_text(encoding="utf-8"))
    runnable = [case for case in fixture["cases"] if case["natural_query"].strip()]
    skipped = len(fixture["cases"]) - len(runnable)
    results = []
    try:
        for index, case in enumerate(runnable, 1):
            print(f"[{index:02d}/{len(runnable)}] {case['id']}", flush=True)
            results.append(score_case(case, parse_search_query(case["natural_query"], model=args.model)))
        report = {"fixture_version": fixture["version"], "summary": summarize(results, skipped_cases=skipped), "cases": results}
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(report["summary"], ensure_ascii=False, indent=2))
    finally:
        if results and not args.keep_audit:
            cleanup_evaluation_rows(results)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
