#!/usr/bin/env python3
"""Fetch and display chunk analysis for a document from the Lenie DB.

Usage:
    cd backend
    python imports/fetch_chunks.py --id 9158                        # List all TEMAT chunks (summary)
    python imports/fetch_chunks.py --id 9158 --text                 # Include full corrected text
    python imports/fetch_chunks.py --id 9158 --pos 5,6,7 --text    # Specific positions with text
    python imports/fetch_chunks.py --id 9158 --list-runs            # Show available analysis runs
    python imports/fetch_chunks.py --id 9158 --run-id 2 --text     # Use specific run
    python imports/fetch_chunks.py --id 9158 --type REKLAMA         # Show ad chunks
"""

import argparse
import sys

# Fix encoding for PowerShell / Windows console
if sys.stdout.encoding and sys.stdout.encoding.lower() in ("cp1250", "cp852", "cp1252"):
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")


def get_runs(session, document_id: int):
    from library.db.models import DocumentAnalysisRun
    return (
        session.query(DocumentAnalysisRun)
        .filter_by(document_id=document_id)
        .order_by(DocumentAnalysisRun.created_at.desc())
        .all()
    )


def get_chunks(session, run_id: int, chunk_type: str | None, positions: list[int] | None):
    from library.db.models import DocumentChunk
    q = session.query(DocumentChunk).filter_by(run_id=run_id)
    if chunk_type:
        q = q.filter_by(type=chunk_type)
    if positions:
        q = q.filter(DocumentChunk.position.in_(positions))
    return q.order_by(DocumentChunk.position).all()


def print_run_header(run, temat_count: int, reklama_count: int, approved_count: int) -> None:
    print(f"\nRun #{run.id} — {run.model} ({run.created_at.strftime('%Y-%m-%d')})")
    print(f"TEMAT: {temat_count}  |  REKLAMA: {reklama_count}  |  APPROVED: {approved_count}")
    print("-" * 70)


def print_chunk(chunk, show_text: bool) -> None:
    status_badge = f"[{chunk.status}]"
    topic = chunk.topic or "(brak tematu)"
    notes = chunk.obsidian_note_paths or []
    notes_badge = f"  [notatki: {', '.join(notes)}]" if notes else ""
    print(f"\n#{chunk.position} {status_badge} {topic}{notes_badge}")
    if chunk.summary:
        print(f"  SUMMARY: {chunk.summary[:300]}{'...' if len(chunk.summary) > 300 else ''}")
    if show_text:
        text = chunk.corrected_text or chunk.original_text or "(brak tekstu)"
        print("  --- TEXT ---")
        for line in text.splitlines():
            print(f"  {line}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Fetch chunk analysis for a Lenie DB document.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--id", type=int, required=True, help="Document ID")
    parser.add_argument("--pos", "--positions", dest="positions",
                        help="Comma-separated chunk positions (default: all)")
    parser.add_argument("--run-id", type=int, help="Specific run ID (default: latest)")
    parser.add_argument("--type", dest="chunk_type", choices=["TEMAT", "REKLAMA"],
                        default="TEMAT", help="Chunk type filter (default: TEMAT)")
    parser.add_argument("--all-types", action="store_true",
                        help="Show all chunk types (overrides --type)")
    parser.add_argument("--text", action="store_true",
                        help="Include full corrected text for each chunk")
    parser.add_argument("--list-runs", action="store_true",
                        help="List available analysis runs and exit")
    args = parser.parse_args()

    from library.db.engine import get_session
    from library.db.models import DocumentChunk

    session = get_session()
    try:
        runs = get_runs(session, args.id)

        if not runs:
            print(f"Brak runów analizy dla dokumentu {args.id}.")
            return

        if args.list_runs:
            print(f"\nRuny analizy dla dokumentu #{args.id}:")
            print("-" * 60)
            for run in runs:
                chunks = session.query(DocumentChunk).filter_by(run_id=run.id).all()
                temat = sum(1 for c in chunks if c.type == "TEMAT")
                reklama = sum(1 for c in chunks if c.type == "REKLAMA")
                approved = sum(1 for c in chunks if c.status == "approved")
                print(
                    f"  Run #{run.id}  {run.created_at.strftime('%Y-%m-%d %H:%M')}  "
                    f"model={run.model}  TEMAT={temat}  REKLAMA={reklama}  approved={approved}"
                )
            return

        # Select run
        if args.run_id:
            run = next((r for r in runs if r.id == args.run_id), None)
            if not run:
                print(f"Run #{args.run_id} nie istnieje dla dokumentu {args.id}.")
                return
        else:
            run = runs[0]

        # Count stats
        all_chunks = session.query(DocumentChunk).filter_by(run_id=run.id).all()
        temat_count = sum(1 for c in all_chunks if c.type == "TEMAT")
        reklama_count = sum(1 for c in all_chunks if c.type == "REKLAMA")
        approved_count = sum(1 for c in all_chunks if c.status == "approved")

        print_run_header(run, temat_count, reklama_count, approved_count)

        # Parse positions
        positions = None
        if args.positions:
            try:
                positions = [int(p.strip()) for p in args.positions.split(",")]
            except ValueError:
                print("Błąd: --pos musi zawierać liczby całkowite oddzielone przecinkami.")
                return

        chunk_type = None if args.all_types else args.chunk_type
        chunks = get_chunks(session, run.id, chunk_type, positions)

        if not chunks:
            print("Brak chunków spełniających podane kryteria.")
            return

        for chunk in chunks:
            print_chunk(chunk, args.text)

        print(f"\n[Łącznie: {len(chunks)} chunków]")

    finally:
        session.close()


if __name__ == "__main__":
    main()
