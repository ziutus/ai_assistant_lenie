#!/usr/bin/env python3
"""One-off backfill: generate embeddings for WhatsApp neighbor profile Documents
(whatsapp_neighbor_profiles.py) created before that script started embedding
them automatically. Pure DB + embedding API operation — does not touch the
WhatsApp export, does not call the LLM extraction/merge pipeline, does not
change text_md.

Usage:
    cd backend
    python imports/whatsapp_neighbor_profiles_backfill_embeddings.py                 # dry-run (default)
    python imports/whatsapp_neighbor_profiles_backfill_embeddings.py --apply
    python imports/whatsapp_neighbor_profiles_backfill_embeddings.py --apply --url-prefix "whatsapp://tuwima-gardens/"
"""

import argparse
import logging
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from imports.whatsapp_neighbor_profiles import _embed_document  # noqa: E402

logger = logging.getLogger("whatsapp_neighbor_profiles_backfill_embeddings")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--url-prefix", default="whatsapp://tuwima-gardens/",
                         help="Only Documents whose url starts with this prefix")
    parser.add_argument("--apply", action="store_true", help="Write embeddings (default: dry-run, lists candidates only)")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO, format="%(levelname)s %(message)s")

    from sqlalchemy import select

    from library.config_loader import load_config
    from library.db.engine import get_session
    from library.db.models import Document, DocumentEmbedding
    from library.document_repository import DocumentRepository

    session = get_session()
    repo = DocumentRepository(session)
    model = load_config().require("EMBEDDING_MODEL")

    docs = list(session.scalars(
        select(Document).where(Document.url.like(f"{args.url_prefix}%")).order_by(Document.id)
    ))
    embedded_ids = set(session.scalars(
        select(DocumentEmbedding.document_id)
        .where(DocumentEmbedding.model == model, DocumentEmbedding.document_id.in_([d.id for d in docs]))
        .distinct()
    ))
    missing = [d for d in docs if d.id not in embedded_ids]

    print(f"Dokumentów pasujących do prefiksu: {len(docs)}")
    print(f"Model embeddingu: {model}")
    print(f"Bez embeddingu: {len(missing)}")

    if not args.apply:
        for d in missing:
            print(f"  #{d.id}  {d.title}")
        print("\n(dry-run — użyj --apply, żeby zapisać embeddingi)")
        session.close()
        return

    total_fragments = 0
    for d in missing:
        n = _embed_document(repo, d, model)
        session.commit()
        total_fragments += n
        logger.info("#%d %s — %d fragmentów", d.id, d.title, n)

    session.close()
    print(f"\nZembedowano dokumentów: {len(missing)}")
    print(f"Łącznie fragmentów: {total_fragments}")


if __name__ == "__main__":
    main()
