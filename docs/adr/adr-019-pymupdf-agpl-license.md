# ADR-019: PDF Text Extraction — PyMuPDF Despite AGPL License Conflict

**Date:** 2026-07-27
**Status:** Accepted (revisit before SaaS)
**Decision Makers:** Ziutus
**Full analysis:** [pdf-library-comparison.md](../pdf-library-comparison.md)

### Context

Importing PDF books into Lenie (`backend/library/book_pdf_import.py`,
`backend/imports/book_import_pdf_twierdza_linux.py`) needs a text-extraction
library that correctly handles soft hyphens, visually-stacked text blocks, and
small-caps fonts — the three failure modes found empirically when testing
`pypdf` against a real technical book ("Twierdza Linux. Bezpieczeństwo dla
dociekliwych", 539 stron). Three libraries were compared on that book:
`pypdf` (BSD-3), `pdfplumber` (MIT), and PyMuPDF/fitz (AGPL-3.0 or paid
commercial license from Artifex).

### Decision

Use **PyMuPDF (fitz)** for PDF text extraction, accepting its AGPL-3.0
license for now.

### Rationale

- **Extraction quality is materially better** for this document type: explicit
  soft-hyphen character (deterministic dehyphenation), correct newline
  insertion between visually stacked elements (`pypdf` silently concatenated
  two chapter headings into one word), and faithful small-caps rendering
  (`pypdf` normalized both variants to uppercase, losing information used by
  downstream regex markers). Full comparison table in
  [pdf-library-comparison.md](../pdf-library-comparison.md).
- **License risk is currently low, not zero.** AGPL-3.0 requires offering full
  application source to anyone who uses the software **over a network** — this
  applies to Lenie because it runs as a server accessed via browser/API. It
  formally conflicts with the project's own BSL 1.1 license (`LICENSE`). The
  decision accepts this because today's deployment is a private,
  non-commercial household installation
  (`docs/deployment/nas/multi-user-household.md`) with only trusted users —
  practical risk is negligible at this scope.
- **Deferred, not ignored.** A private-repo note
  (`lenie-bmad-private/docs/deployment/commercial-multi-tenant-scaling-experiment.md`,
  §2a) tracks this as a dependency requiring re-review before Lenie could
  become a hosted/SaaS service for untrusted external users — out of scope for
  the public repo but the trigger condition is recorded there.

### Consequences

- **Positive:** Best available extraction quality for technical books (lists,
  code blocks, config blocks interleaved with prose) without hand-rolled
  workarounds.
- **Negative:** Formal license conflict with the project's BSL 1.1 exists
  today, even though practical exposure is minimal at current (private,
  non-commercial) scope.
- **Deferred:** Before any hosted/SaaS offering, this decision must be
  revisited. Options at that point: purchase a commercial PyMuPDF license from
  Artifex, migrate to `pdfplumber` (MIT, worse column-alignment fidelity for
  code/config blocks), or do a full dependency-tree license audit
  (AGPL/GPL/SSPL) rather than a point fix.
- **Unaffected:** `check_pdf_text_layer.py` keeps using `pypdf` — it only
  needs a yes/no "does a text layer exist" check, not extraction quality.

### Related Artifacts

- [pdf-library-comparison.md](../pdf-library-comparison.md) — full
  library comparison, empirical failure examples, paragraph-break heuristic
  used on top of PyMuPDF's output
- `backend/library/book_pdf_import.py` — implementation
- `backend/imports/book_import_pdf_twierdza_linux.py` — reference import script
- `lenie-bmad-private/docs/deployment/commercial-multi-tenant-scaling-experiment.md`
  §2a (private repo) — SaaS-scope trigger condition and revisit options
