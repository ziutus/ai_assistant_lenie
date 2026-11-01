"""create geopolitics tables (countries, geo events, directed relation assessments)

Revision ID: d7e1a4b9c205
Revises: c5a1d9e7f204
Create Date: 2026-11-01 00:00:00.000000

ADR-033. Source-backed world events plus versioned, directed assessments of the
relation between two countries (``from`` country's stance toward ``to`` country
on one axis, over a validity period). The map shows only ``confirmed``
assessments; an LLM or a human proposes, one click confirms.

``countries`` is a frozen seed of the closed gazetteer list
(``library/country_gazetteer.py``) so the relation tables can use real FKs.
``iso3`` is NULL for Kosovo, which has no official ISO 3166-1 code;
``map_code`` is what ``public/geo/world-countries.geo.json`` is keyed by.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "d7e1a4b9c205"
down_revision: Union[str, None] = "c5a1d9e7f204"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# (slug, name_pl, map_code) — frozen copy of the gazetteer; do not import app code here.
_COUNTRIES = [
    ('polska', 'Polska', 'POL'),
    ('niemcy', 'Niemcy', 'DEU'),
    ('francja', 'Francja', 'FRA'),
    ('wielka-brytania', 'Wielka Brytania', 'GBR'),
    ('wlochy', 'Włochy', 'ITA'),
    ('hiszpania', 'Hiszpania', 'ESP'),
    ('portugalia', 'Portugalia', 'PRT'),
    ('holandia', 'Holandia', 'NLD'),
    ('belgia', 'Belgia', 'BEL'),
    ('szwajcaria', 'Szwajcaria', 'CHE'),
    ('austria', 'Austria', 'AUT'),
    ('szwecja', 'Szwecja', 'SWE'),
    ('norwegia', 'Norwegia', 'NOR'),
    ('dania', 'Dania', 'DNK'),
    ('finlandia', 'Finlandia', 'FIN'),
    ('islandia', 'Islandia', 'ISL'),
    ('irlandia', 'Irlandia', 'IRL'),
    ('grecja', 'Grecja', 'GRC'),
    ('cypr', 'Cypr', 'CYP'),
    ('malta', 'Malta', 'MLT'),
    ('czechy', 'Czechy', 'CZE'),
    ('slowacja', 'Słowacja', 'SVK'),
    ('wegry', 'Węgry', 'HUN'),
    ('rumunia', 'Rumunia', 'ROU'),
    ('bulgaria', 'Bułgaria', 'BGR'),
    ('chorwacja', 'Chorwacja', 'HRV'),
    ('slowenia', 'Słowenia', 'SVN'),
    ('bosnia-i-hercegowina', 'Bośnia i Hercegowina', 'BIH'),
    ('serbia', 'Serbia', 'SRB'),
    ('czarnogora', 'Czarnogóra', 'MNE'),
    ('macedonia-polnocna', 'Macedonia Północna', 'MKD'),
    ('albania', 'Albania', 'ALB'),
    ('kosowo', 'Kosowo', 'XKX'),
    ('moldawia', 'Mołdawia', 'MDA'),
    ('ukraina', 'Ukraina', 'UKR'),
    ('bialorus', 'Białoruś', 'BLR'),
    ('litwa', 'Litwa', 'LTU'),
    ('lotwa', 'Łotwa', 'LVA'),
    ('estonia', 'Estonia', 'EST'),
    ('rosja', 'Rosja', 'RUS'),
    ('andora', 'Andora', 'AND'),
    ('monako', 'Monako', 'MCO'),
    ('san-marino', 'San Marino', 'SMR'),
    ('liechtenstein', 'Liechtenstein', 'LIE'),
    ('watykan', 'Watykan', 'VAT'),
    ('luksemburg', 'Luksemburg', 'LUX'),
    ('chiny', 'Chiny', 'CHN'),
    ('japonia', 'Japonia', 'JPN'),
    ('korea-poludniowa', 'Korea Południowa', 'KOR'),
    ('korea-polnocna', 'Korea Północna', 'PRK'),
    ('indie', 'Indie', 'IND'),
    ('pakistan', 'Pakistan', 'PAK'),
    ('bangladesz', 'Bangladesz', 'BGD'),
    ('sri-lanka', 'Sri Lanka', 'LKA'),
    ('nepal', 'Nepal', 'NPL'),
    ('bhutan', 'Bhutan', 'BTN'),
    ('malediwy', 'Malediwy', 'MDV'),
    ('afganistan', 'Afganistan', 'AFG'),
    ('iran', 'Iran', 'IRN'),
    ('irak', 'Irak', 'IRQ'),
    ('arabia-saudyjska', 'Arabia Saudyjska', 'SAU'),
    ('jemen', 'Jemen', 'YEM'),
    ('oman', 'Oman', 'OMN'),
    ('zjednoczone-emiraty-arabskie', 'Zjednoczone Emiraty Arabskie', 'ARE'),
    ('katar', 'Katar', 'QAT'),
    ('bahrajn', 'Bahrajn', 'BHR'),
    ('kuwejt', 'Kuwejt', 'KWT'),
    ('jordania', 'Jordania', 'JOR'),
    ('liban', 'Liban', 'LBN'),
    ('syria', 'Syria', 'SYR'),
    ('izrael', 'Izrael', 'ISR'),
    ('palestyna', 'Palestyna', 'PSE'),
    ('turcja', 'Turcja', 'TUR'),
    ('gruzja', 'Gruzja', 'GEO'),
    ('armenia', 'Armenia', 'ARM'),
    ('azerbejdzan', 'Azerbejdżan', 'AZE'),
    ('kazachstan', 'Kazachstan', 'KAZ'),
    ('uzbekistan', 'Uzbekistan', 'UZB'),
    ('turkmenistan', 'Turkmenistan', 'TKM'),
    ('tadzykistan', 'Tadżykistan', 'TJK'),
    ('kirgistan', 'Kirgistan', 'KGZ'),
    ('mongolia', 'Mongolia', 'MNG'),
    ('tajwan', 'Tajwan', 'TWN'),
    ('wietnam', 'Wietnam', 'VNM'),
    ('laos', 'Laos', 'LAO'),
    ('kambodza', 'Kambodża', 'KHM'),
    ('tajlandia', 'Tajlandia', 'THA'),
    ('mjanma', 'Mjanma', 'MMR'),
    ('malezja', 'Malezja', 'MYS'),
    ('singapur', 'Singapur', 'SGP'),
    ('indonezja', 'Indonezja', 'IDN'),
    ('filipiny', 'Filipiny', 'PHL'),
    ('brunei', 'Brunei', 'BRN'),
    ('timor-wschodni', 'Timor Wschodni', 'TLS'),
    ('egipt', 'Egipt', 'EGY'),
    ('libia', 'Libia', 'LBY'),
    ('tunezja', 'Tunezja', 'TUN'),
    ('algieria', 'Algieria', 'DZA'),
    ('maroko', 'Maroko', 'MAR'),
    ('sahara-zachodnia', 'Sahara Zachodnia', 'ESH'),
    ('mauretania', 'Mauretania', 'MRT'),
    ('mali', 'Mali', 'MLI'),
    ('niger', 'Niger', 'NER'),
    ('nigeria', 'Nigeria', 'NGA'),
    ('czad', 'Czad', 'TCD'),
    ('sudan', 'Sudan', 'SDN'),
    ('sudan-poludniowy', 'Sudan Południowy', 'SSD'),
    ('erytrea', 'Erytrea', 'ERI'),
    ('dzibuti', 'Dżibuti', 'DJI'),
    ('etiopia', 'Etiopia', 'ETH'),
    ('somalia', 'Somalia', 'SOM'),
    ('kenia', 'Kenia', 'KEN'),
    ('uganda', 'Uganda', 'UGA'),
    ('tanzania', 'Tanzania', 'TZA'),
    ('rwanda', 'Rwanda', 'RWA'),
    ('burundi', 'Burundi', 'BDI'),
    ('demokratyczna-republika-konga', 'Demokratyczna Republika Konga', 'COD'),
    ('republika-konga', 'Republika Konga', 'COG'),
    ('gabon', 'Gabon', 'GAB'),
    ('gwinea-rownikowa', 'Gwinea Równikowa', 'GNQ'),
    ('kamerun', 'Kamerun', 'CMR'),
    ('republika-srodkowoafrykanska', 'Republika Środkowoafrykańska', 'CAF'),
    ('benin', 'Benin', 'BEN'),
    ('togo', 'Togo', 'TGO'),
    ('ghana', 'Ghana', 'GHA'),
    ('wybrzeze-kosci-sloniowej', 'Wybrzeże Kości Słoniowej', 'CIV'),
    ('liberia', 'Liberia', 'LBR'),
    ('sierra-leone', 'Sierra Leone', 'SLE'),
    ('gwinea', 'Gwinea', 'GIN'),
    ('gwinea-bissau', 'Gwinea Bissau', 'GNB'),
    ('senegal', 'Senegal', 'SEN'),
    ('gambia', 'Gambia', 'GMB'),
    ('republika-zielonego-przyladka', 'Republika Zielonego Przylądka', 'CPV'),
    ('burkina-faso', 'Burkina Faso', 'BFA'),
    ('angola', 'Angola', 'AGO'),
    ('zambia', 'Zambia', 'ZMB'),
    ('zimbabwe', 'Zimbabwe', 'ZWE'),
    ('mozambik', 'Mozambik', 'MOZ'),
    ('malawi', 'Malawi', 'MWI'),
    ('madagaskar', 'Madagaskar', 'MDG'),
    ('mauritius', 'Mauritius', 'MUS'),
    ('seszele', 'Seszele', 'SYC'),
    ('komory', 'Komory', 'COM'),
    ('botswana', 'Botswana', 'BWA'),
    ('namibia', 'Namibia', 'NAM'),
    ('eswatini', 'Eswatini', 'SWZ'),
    ('lesotho', 'Lesotho', 'LSO'),
    ('republika-poludniowej-afryki', 'Republika Południowej Afryki', 'ZAF'),
    ('stany-zjednoczone', 'Stany Zjednoczone', 'USA'),
    ('kanada', 'Kanada', 'CAN'),
    ('meksyk', 'Meksyk', 'MEX'),
    ('gwatemala', 'Gwatemala', 'GTM'),
    ('belize', 'Belize', 'BLZ'),
    ('honduras', 'Honduras', 'HND'),
    ('salwador', 'Salwador', 'SLV'),
    ('nikaragua', 'Nikaragua', 'NIC'),
    ('kostaryka', 'Kostaryka', 'CRI'),
    ('panama', 'Panama', 'PAN'),
    ('kuba', 'Kuba', 'CUB'),
    ('jamajka', 'Jamajka', 'JAM'),
    ('haiti', 'Haiti', 'HTI'),
    ('dominikana', 'Dominikana', 'DOM'),
    ('bahamy', 'Bahamy', 'BHS'),
    ('barbados', 'Barbados', 'BRB'),
    ('trynidad-i-tobago', 'Trynidad i Tobago', 'TTO'),
    ('antigua-i-barbuda', 'Antigua i Barbuda', 'ATG'),
    ('saint-kitts-i-nevis', 'Saint Kitts i Nevis', 'KNA'),
    ('dominika', 'Dominika', 'DMA'),
    ('saint-lucia', 'Saint Lucia', 'LCA'),
    ('saint-vincent-i-grenadyny', 'Saint Vincent i Grenadyny', 'VCT'),
    ('grenada', 'Grenada', 'GRD'),
    ('kolumbia', 'Kolumbia', 'COL'),
    ('wenezuela', 'Wenezuela', 'VEN'),
    ('gujana', 'Gujana', 'GUY'),
    ('surinam', 'Surinam', 'SUR'),
    ('ekwador', 'Ekwador', 'ECU'),
    ('peru', 'Peru', 'PER'),
    ('brazylia', 'Brazylia', 'BRA'),
    ('boliwia', 'Boliwia', 'BOL'),
    ('paragwaj', 'Paragwaj', 'PRY'),
    ('chile', 'Chile', 'CHL'),
    ('argentyna', 'Argentyna', 'ARG'),
    ('urugwaj', 'Urugwaj', 'URY'),
    ('australia', 'Australia', 'AUS'),
    ('nowa-zelandia', 'Nowa Zelandia', 'NZL'),
    ('papua-nowa-gwinea', 'Papua-Nowa Gwinea', 'PNG'),
    ('fidzi', 'Fidżi', 'FJI'),
    ('wyspy-salomona', 'Wyspy Salomona', 'SLB'),
    ('vanuatu', 'Vanuatu', 'VUT'),
    ('samoa', 'Samoa', 'WSM'),
    ('tonga', 'Tonga', 'TON'),
    ('kiribati', 'Kiribati', 'KIR'),
    ('tuvalu', 'Tuvalu', 'TUV'),
    ('nauru', 'Nauru', 'NRU'),
    ('palau', 'Palau', 'PLW'),
    ('mikronezja', 'Mikronezja', 'FSM'),
    ('wyspy-marshalla', 'Wyspy Marshalla', 'MHL'),
]

_DISPUTED = {"XKX": "disputed", "TWN": "disputed", "PSE": "disputed", "ESH": "disputed"}


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS btree_gist")

    countries = op.create_table(
        "countries",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("slug", sa.String(length=80), nullable=False),
        sa.Column("name_pl", sa.String(length=120), nullable=False),
        sa.Column("iso3", sa.String(length=3), nullable=True),
        sa.Column("map_code", sa.String(length=3), nullable=False),
        sa.Column("entity_kind", sa.String(length=20), nullable=False, server_default="state"),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.UniqueConstraint("slug", name="uq_countries_slug"),
        sa.UniqueConstraint("iso3", name="uq_countries_iso3"),
        sa.UniqueConstraint("map_code", name="uq_countries_map_code"),
        sa.CheckConstraint("entity_kind IN ('state', 'disputed', 'territory')", name="ck_countries_kind"),
    )
    op.bulk_insert(
        countries,
        [
            {
                "slug": slug,
                "name_pl": name,
                "iso3": None if code == "XKX" else code,
                "map_code": code,
                "entity_kind": _DISPUTED.get(code, "state"),
            }
            for slug, name, code in _COUNTRIES
        ],
    )

    op.create_table(
        "geo_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("event_date", sa.Date(), nullable=False),
        sa.Column("event_date_end", sa.Date(), nullable=True),
        sa.Column("date_precision", sa.String(length=10), nullable=False, server_default="day"),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="proposed"),
        sa.Column("detection_method", sa.String(length=20), nullable=False, server_default="manual"),
        sa.Column("model", sa.String(length=120), nullable=True),
        sa.Column("dedup_key", sa.String(length=64), nullable=True),
        sa.Column(
            "created_by_user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True
        ),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("decided_at", sa.DateTime(), nullable=True),
        sa.Column(
            "decided_by_user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True
        ),
        sa.CheckConstraint("status IN ('proposed', 'confirmed', 'rejected')", name="ck_geo_events_status"),
        sa.CheckConstraint("date_precision IN ('day', 'month', 'year')", name="ck_geo_events_precision"),
        sa.CheckConstraint("event_date_end IS NULL OR event_date_end >= event_date", name="ck_geo_events_dates"),
    )
    op.create_index("idx_geo_events_status_date", "geo_events", ["status", "event_date"])
    op.create_index("idx_geo_events_dedup_key", "geo_events", ["dedup_key"])

    op.create_table(
        "geo_event_participants",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("event_id", sa.Integer(), sa.ForeignKey("geo_events.id", ondelete="CASCADE"), nullable=False),
        sa.Column("country_id", sa.Integer(), sa.ForeignKey("countries.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("role", sa.String(length=20), nullable=False),
        sa.UniqueConstraint("event_id", "country_id", "role", name="uq_geo_event_participants"),
        sa.CheckConstraint("role IN ('actor', 'target', 'affected', 'location')", name="ck_geo_event_participants_role"),
    )
    op.create_index("idx_geo_event_participants_country", "geo_event_participants", ["country_id", "event_id"])

    op.create_table(
        "geo_event_sources",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("event_id", sa.Integer(), sa.ForeignKey("geo_events.id", ondelete="CASCADE"), nullable=False),
        # RESTRICT: deleting an article must not silently destroy the grounds of a confirmed assessment.
        sa.Column("document_id", sa.Integer(), sa.ForeignKey("documents.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("anchor_quote", sa.Text(), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("stance", sa.String(length=20), nullable=False, server_default="supports"),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("event_id", "document_id", "content_hash", name="uq_geo_event_sources"),
        sa.CheckConstraint("stance IN ('supports', 'disputes')", name="ck_geo_event_sources_stance"),
    )
    op.create_index("idx_geo_event_sources_document", "geo_event_sources", ["document_id"])

    op.create_table(
        "country_relation_assessments",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("from_country_id", sa.Integer(), sa.ForeignKey("countries.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("to_country_id", sa.Integer(), sa.ForeignKey("countries.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("axis", sa.String(length=20), nullable=False),
        sa.Column("score", sa.SmallInteger(), nullable=False),
        sa.Column("confidence", sa.Numeric(3, 2), nullable=False, server_default="0.50"),
        sa.Column("valid_from", sa.Date(), nullable=False),
        sa.Column("valid_to", sa.Date(), nullable=True),
        sa.Column("review_due_at", sa.Date(), nullable=True),
        sa.Column("rationale", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="proposed"),
        sa.Column("detection_method", sa.String(length=20), nullable=False, server_default="manual"),
        sa.Column("model", sa.String(length=120), nullable=True),
        sa.Column(
            "supersedes_id",
            sa.Integer(),
            sa.ForeignKey("country_relation_assessments.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column(
            "created_by_user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True
        ),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("decided_at", sa.DateTime(), nullable=True),
        sa.Column(
            "decided_by_user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True
        ),
        sa.CheckConstraint("from_country_id <> to_country_id", name="ck_country_relation_distinct"),
        sa.CheckConstraint("axis IN ('political', 'security')", name="ck_country_relation_axis"),
        sa.CheckConstraint("score BETWEEN -2 AND 2", name="ck_country_relation_score"),
        sa.CheckConstraint("confidence BETWEEN 0 AND 1", name="ck_country_relation_confidence"),
        sa.CheckConstraint("valid_to IS NULL OR valid_to > valid_from", name="ck_country_relation_period"),
        sa.CheckConstraint(
            "status IN ('proposed', 'confirmed', 'rejected')", name="ck_country_relation_status"
        ),
    )
    op.create_index(
        "idx_country_relation_from", "country_relation_assessments", ["from_country_id", "axis", "valid_from"]
    )
    op.create_index(
        "idx_country_relation_to", "country_relation_assessments", ["to_country_id", "axis", "valid_from"]
    )
    op.create_index("idx_country_relation_status", "country_relation_assessments", ["status", "created_at"])
    # Confirmed periods of one (from, to, axis) must never overlap; the service closes the previous
    # period in the same transaction, this constraint is the concurrency backstop.
    op.execute(
        """
        ALTER TABLE country_relation_assessments
        ADD CONSTRAINT ex_country_relation_no_overlap
        EXCLUDE USING gist (
            from_country_id WITH =,
            to_country_id WITH =,
            axis WITH =,
            daterange(valid_from, valid_to, '[)') WITH &&
        ) WHERE (status = 'confirmed')
        """
    )

    op.create_table(
        "country_relation_evidence",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "assessment_id",
            sa.Integer(),
            sa.ForeignKey("country_relation_assessments.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("event_id", sa.Integer(), sa.ForeignKey("geo_events.id", ondelete="CASCADE"), nullable=False),
        sa.Column("stance", sa.String(length=20), nullable=False, server_default="supports"),
        sa.UniqueConstraint("assessment_id", "event_id", name="uq_country_relation_evidence"),
        sa.CheckConstraint("stance IN ('supports', 'contradicts')", name="ck_country_relation_evidence_stance"),
    )
    op.create_index("idx_country_relation_evidence_event", "country_relation_evidence", ["event_id"])


def downgrade() -> None:
    op.drop_table("country_relation_evidence")
    op.drop_table("country_relation_assessments")
    op.drop_table("geo_event_sources")
    op.drop_table("geo_event_participants")
    op.drop_table("geo_events")
    op.drop_table("countries")
