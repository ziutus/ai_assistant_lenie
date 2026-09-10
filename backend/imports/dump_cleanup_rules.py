"""Zapisz deterministyczny snapshot cleanup_rules do fixtury repozytorium."""

import argparse
import json
from pathlib import Path

from sqlalchemy import text

from library.db.engine import get_session

DEFAULT_OUT = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "cleanup_rules.json"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()
    session = get_session()
    try:
        rows = [dict(row) for row in session.execute(text("SELECT * FROM cleanup_rules ORDER BY id")).mappings()]
        args.out.write_text(
            json.dumps(rows, sort_keys=True, indent=2, ensure_ascii=False, default=str) + "\n",
            encoding="utf-8",
        )
    finally:
        session.close()


if __name__ == "__main__":
    main()
