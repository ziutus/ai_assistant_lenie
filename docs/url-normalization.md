# Document URL normalization

Documents retain two URL values:

- `url` is the original address used for display and fetching;
- `canonical_url` is the stable comparison key used by `Document.get_by_url()` and duplicate detection.

The shared implementation is `backend/library/url_normalization.py`. All ORM assignments to `Document.url` populate `canonical_url` automatically.

## Rules

Normalization is deliberately conservative:

- trim surrounding whitespace;
- lowercase the scheme and hostname and remove a trailing hostname dot;
- encode international hostnames with IDNA;
- remove default ports 80/443;
- remove the `#fragment`;
- remove known tracking parameters (`utm_*`, `fbclid`, `gclid`, `msclkid`, and related identifiers);
- retain content-selecting query parameters and sort them deterministically;
- normalize empty paths and trailing slashes;
- map common YouTube watch and `youtu.be` forms to one identity.

The implementation does not globally equate `http` with `https` or an apex domain with `www`, because those addresses can represent different resources.

## Database migration

Migration `e2f3a4b5c6d7_add_documents_canonical_url.py` adds and backfills the column. During upgrade it prints every normalized address shared by multiple historical documents as:

```text
CANONICAL URL COLLISION: <canonical-url> -> document IDs [<id>, ...]
```

The migration does not delete or merge anything and creates a non-unique index. Review each collision before introducing a unique constraint, because chunks, analyses, embeddings, notes, and review state may be attached to different records.

## Submission behavior

A normal submission whose canonical URL already exists returns the existing document ID and does not store or analyze another document. Captured HTML can only be attached through `fill_missing_html`, and only if the existing document has no `text_raw`. This operation does not trigger paid LLM processing.
