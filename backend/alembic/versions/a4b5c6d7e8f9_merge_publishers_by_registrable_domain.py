"""Merge publishers sharing a registrable domain (eTLD+1).

Backfill migration f5a6b7c8d9e0 (2026-07-18) created one publisher per raw
URL hostname, so every subdomain got its own row. For sites that publish
under multiple subdomains of the *same organization's own* domain
(wiadomosci.wp.pl, tech.wp.pl, ... -> all really "WP") that fragmented one
real publisher into many: checked live on NAS 2026-07-20, 84% of 3904
publishers had exactly one document — mostly this fragmentation, not
genuinely distinct one-off portals.

Recomputes each publisher_domains.domain's registrable domain via
library.publisher_domain.registrable_domain() — Public Suffix List-aware
(see that module's docstring for why a naive "last two labels" split would
be wrong: it would merge unrelated Polish government agencies sharing
gov.pl, or unrelated companies sharing com.pl/co.uk, while failing to keep
apart per-author subdomains on hosting platforms like github.io or
substack.com). This migration deliberately imports application code (unlike
most migrations in this repo, which duplicate their transform logic inline
to stay self-contained) because the whole point is for this one-time
backfill to group publishers *exactly* the way Document.set_publisher_from_
url() will group them for every future import — any divergence here would
silently re-fragment new documents from old ones.

For each registrable-domain group spanning more than one existing publisher:
- survivor = the publisher whose own domain already equals the registrable
  domain, if one exists; otherwise the publisher with the most documents,
  ties broken by lowest id.
- every publisher_domains row in the group is re-pointed to the survivor
  first (so resolve_publisher(domain=...) keeps matching every original
  subdomain, and so deleting the losing publishers doesn't cascade-delete
  domains still in use).
- every documents.publisher_id in the group is re-pointed to the survivor.
- the survivor's canonical_name becomes the registrable domain.
- the now-unreferenced losing publisher rows are deleted.

A merged group's original hostnames were all subdomains (nobody had linked
to the bare registrable domain itself), so the survivor's own
canonical_name may not exist as one of its publisher_domains rows after
the merge — e.g. tech.wp.pl/wiadomosci.wp.pl/... merge into canonical_name
"wp.pl", but no publisher_domains row literally says "wp.pl", so
resolve_publisher(domain="wp.pl") / the /search publisher_domain filter
would silently match nothing (caught live on NAS: 30 of 96 merged
publishers had this gap). A final pass backfills that missing row for
every publisher — merged or not — matching Publisher.ensure()'s own
invariant that a publisher's canonical_name is always also one of its
publisher_domains.domain values.

Every merge is printed (registrable domain <- old canonical names) for
audit, mirroring the collision report in e2f3a4b5c6d7 (canonical_url).

Not reversible to the exact pre-migration fragmentation — that fragmentation
was the bug, not state worth restoring. downgrade() only drops the schema
knowledge of having run this pass.

Revision ID: a4b5c6d7e8f9
Revises: f3a4b5c6d7e8
"""
from alembic import op
import sqlalchemy as sa

revision = "a4b5c6d7e8f9"
down_revision = "f3a4b5c6d7e8"
branch_labels = None
depends_on = None


def upgrade():
    from library.publisher_domain import registrable_domain

    connection = op.get_bind()
    publisher_name_by_id = dict(connection.execute(
        sa.text("SELECT id, canonical_name FROM publishers")
    ).fetchall())
    doc_count_by_publisher = dict(connection.execute(sa.text(
        "SELECT publisher_id, count(*) FROM documents"
        " WHERE publisher_id IS NOT NULL GROUP BY publisher_id"
    )).fetchall())
    domain_rows = connection.execute(
        sa.text("SELECT id, publisher_id, domain FROM publisher_domains")
    ).fetchall()

    groups: dict[str, list[tuple[int, int, str]]] = {}
    for domain_id, publisher_id, domain in domain_rows:
        reg_domain = registrable_domain(domain) or domain
        groups.setdefault(reg_domain, []).append((domain_id, publisher_id, domain))

    for reg_domain, rows in sorted(groups.items()):
        publisher_ids = {publisher_id for _, publisher_id, _ in rows}
        if len(publisher_ids) <= 1:
            continue

        survivor_id = next(
            (publisher_id for _, publisher_id, domain in rows if domain == reg_domain),
            max(publisher_ids, key=lambda pid: (doc_count_by_publisher.get(pid, 0), -pid)),
        )
        losing_ids = publisher_ids - {survivor_id}

        for domain_id, publisher_id, _ in rows:
            if publisher_id != survivor_id:
                connection.execute(
                    sa.text("UPDATE publisher_domains SET publisher_id = :survivor WHERE id = :id"),
                    {"survivor": survivor_id, "id": domain_id},
                )
        for losing_id in losing_ids:
            connection.execute(
                sa.text("UPDATE documents SET publisher_id = :survivor WHERE publisher_id = :losing"),
                {"survivor": survivor_id, "losing": losing_id},
            )
        connection.execute(
            sa.text("UPDATE publishers SET canonical_name = :name WHERE id = :id"),
            {"name": reg_domain, "id": survivor_id},
        )
        for losing_id in losing_ids:
            connection.execute(sa.text("DELETE FROM publishers WHERE id = :id"), {"id": losing_id})

        old_names = sorted({publisher_name_by_id[pid] for pid in publisher_ids})
        print(f"PUBLISHER MERGE: {reg_domain} <- {old_names}")

    connection.execute(sa.text("""
        INSERT INTO publisher_domains (publisher_id, domain)
        SELECT p.id, p.canonical_name
        FROM publishers p
        WHERE NOT EXISTS (
            SELECT 1 FROM publisher_domains pd
            WHERE pd.publisher_id = p.id AND pd.domain = p.canonical_name
        )
        AND NOT EXISTS (
            SELECT 1 FROM publisher_domains pd2 WHERE pd2.domain = p.canonical_name
        )
    """))


def downgrade():
    pass
