"""Parse a printed card book into cards.json and review.csv, without database access."""

import argparse
import json
import pathlib
import sys
from collections import Counter

from library.project_card_family_parser import parse_card_pdf, valid_numbering, write_review_csv


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pdf", type=pathlib.Path)
    parser.add_argument("--series", required=True)
    parser.add_argument("--kind", required=True, choices=("experiment", "craft", "puzzle"))
    parser.add_argument("--age-min", type=int)
    parser.add_argument("--age-max", type=int)
    parser.add_argument("--out-dir", type=pathlib.Path)
    args = parser.parse_args(argv)
    if not args.pdf.is_file():
        parser.error(f"Not a PDF file: {args.pdf}")
    for age in (args.age_min, args.age_max):
        if age is not None and not 0 <= age <= 18:
            parser.error("Ages must be between 0 and 18")
    if args.age_min is not None and args.age_max is not None and args.age_min > args.age_max:
        parser.error("--age-min cannot exceed --age-max")
    inventory = Counter()
    cards = parse_card_pdf(args.pdf, series=args.series, kind=args.kind, age_min=args.age_min,
                           age_max=args.age_max, inventory=inventory)
    out = args.out_dir or pathlib.Path("tmp/project_card_families/out") / args.pdf.stem
    out.mkdir(parents=True, exist_ok=True)
    (out / "cards.json").write_text(json.dumps(cards, ensure_ascii=False, indent=2), encoding="utf-8")
    write_review_csv(cards, out / "review.csv")
    print(f"cards={len(cards)} flagged={sum(bool(card['flags']) for card in cards)}")
    for (header, role), count in sorted(inventory.items()):
        print(f"{header};{role};{count}")
    if not valid_numbering(cards):
        print("Card numbering has gaps, duplicates or does not match the highest №", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
