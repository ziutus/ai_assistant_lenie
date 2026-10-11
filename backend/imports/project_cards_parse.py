"""CLI: parse a directory of project-card PDFs into cards.json + review.csv.

Thin wrapper — all logic lives in library/project_card_parser.py. No database
or network access: it only reads PDFs and writes two files. Send the result to
Lenie with POST /project_cards/import (see backend/CLAUDE.md, "Project cards").

The PDFs are one card per file named "NNN - Title.pdf" (the three-digit prefix
becomes the card number). A PDF that fails to parse becomes a PARSE_ERROR
record instead of aborting the run.

Running:
    cd backend
    python imports/project_cards_parse.py "H:/path/to/cards" --out-dir tmp/project_cards/out
"""

import argparse
import json
import pathlib
import sys

from library.project_card_parser import parse_card_dir, write_review_csv


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("pdf_dir", type=pathlib.Path, help="directory with NNN - Title.pdf files")
    parser.add_argument("--out-dir", type=pathlib.Path, default=pathlib.Path("tmp/project_cards/out"),
                        help="where cards.json and review.csv are written (default: tmp/project_cards/out)")
    args = parser.parse_args(argv)

    if not args.pdf_dir.is_dir():
        print(f"Not a directory: {args.pdf_dir}", file=sys.stderr)
        return 2
    cards = parse_card_dir(args.pdf_dir)
    if not cards:
        print(f"No *.pdf files in {args.pdf_dir}", file=sys.stderr)
        return 1

    args.out_dir.mkdir(parents=True, exist_ok=True)
    (args.out_dir / "cards.json").write_text(json.dumps(cards, ensure_ascii=False, indent=2), encoding="utf-8")
    write_review_csv(cards, args.out_dir / "review.csv")
    flagged = sum(1 for card in cards if card["flags"])
    print(f"cards={len(cards)} flagged={flagged} -> {args.out_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
