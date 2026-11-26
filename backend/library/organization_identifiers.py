"""Human-entered registry numbers; callers own the transaction."""

import re
from urllib.parse import urlsplit

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from library.company_registry_service import normalize_krs, normalize_nip
from library.db.models import Organization, OrganizationIdentifier

# ISO 3166-1 alpha-2, plus the explicit international-number namespace.
COUNTRIES = set("AD AE AF AG AI AL AM AO AQ AR AS AT AU AW AX AZ BA BB BD BE BF BG BH BI BJ BL BM BN BO BQ BR BS BT BV BW BY BZ CA CC CD CF CG CH CI CK CL CM CN CO CR CU CV CW CX CY CZ DE DJ DK DM DO DZ EC EE EG EH ER ES ET FI FJ FK FM FO FR GA GB GD GE GF GG GH GI GL GM GN GP GQ GR GS GT GU GW GY HK HM HN HR HT HU ID IE IL IM IN IO IQ IR IS IT JE JM JO JP KE KG KH KI KM KN KP KR KW KY KZ LA LB LC LI LK LR LS LT LU LV LY MA MC MD ME MF MG MH MK ML MM MN MO MP MQ MR MS MT MU MV MW MX MY MZ NA NC NE NF NG NI NL NO NP NR NU NZ OM PA PE PF PG PH PK PL PM PN PR PS PT PW PY QA RE RO RS RU RW SA SB SC SD SE SG SH SI SJ SK SL SM SN SO SR SS ST SV SX SY SZ TC TD TF TG TH TJ TK TL TM TN TO TR TT TV TW TZ UA UG UM US UY UZ VA VC VE VG VI VN VU WF WS YE YT ZA ZM ZW XX".split())


# Fixed texts: the route answers with these, never with an exception's own content.
ERRORS = {
    "not_text": "Kraj, typ i numer muszą być tekstem.",
    "country": "Podaj dwuliterowy kod kraju ISO lub XX.",
    "type": "Nieprawidłowy typ numeru. Nie zapisujemy numerów PESEL.",
    "nip": "NIP musi zawierać 10 cyfr i poprawną sumę kontrolną.",
    "krs": "KRS musi zawierać od 1 do 10 cyfr.",
    "regon_length": "REGON musi zawierać 9 lub 14 cyfr.",
    "regon_checksum": "Nieprawidłowa suma kontrolna REGON.",
    "value": "Numer musi mieć od 1 do 100 znaków.",
    "body": "Podaj obiekt z krajem, typem i numerem.",
    "optional_text": "Adres źródła i notatka muszą być tekstem.",
    "source_url": "Adres źródła musi być adresem HTTP lub HTTPS bez danych logowania.",
}


class IdentifierError(ValueError):
    def __init__(self, code):
        super().__init__(ERRORS[code])
        self.code = code


class IdentifierConflict(ValueError):
    def __init__(self, organization):
        super().__init__("Ten numer jest już przypisany do innej organizacji.")
        self.conflict_organization = {"id": organization.id, "canonical_name": organization.canonical_name}


def normalize_identifier(country_code, identifier_type, value):
    if not all(isinstance(v, str) for v in (country_code, identifier_type, value)):
        raise IdentifierError("not_text")
    country_code, identifier_type = country_code.strip().upper(), identifier_type.strip().lower()
    if country_code not in COUNTRIES:
        raise IdentifierError("country")
    if not re.fullmatch(r"[a-z0-9_]{1,30}", identifier_type) or identifier_type == "pesel":
        raise IdentifierError("type")
    value = " ".join(value.split()).upper()
    if country_code == "PL" and identifier_type in ("nip", "krs"):
        normalize = normalize_nip if identifier_type == "nip" else normalize_krs
        try:
            value = normalize(value)
        except ValueError:
            raise IdentifierError(identifier_type) from None
    elif country_code == "PL" and identifier_type == "regon":
        value = re.sub(r"[\s.-]", "", value)
        if not re.fullmatch(r"(?:[0-9]{9}|[0-9]{14})", value):
            raise IdentifierError("regon_length")
        def valid(number, weights):
            return (sum(int(n) * w for n, w in zip(number, weights)) % 11) % 10 == int(number[-1])
        if not valid(value[:9], (8, 9, 2, 3, 4, 5, 6, 7)) or (
            len(value) == 14 and not valid(value, (2, 4, 8, 5, 0, 9, 7, 3, 6, 1, 2, 4, 8))
        ):
            raise IdentifierError("regon_checksum")
    if not 1 <= len(value) <= 100:
        raise IdentifierError("value")
    return country_code, identifier_type, value


def serialize(row):
    return {key: getattr(row, key) for key in
            ("id", "organization_id", "country_code", "identifier_type", "value", "source_url", "note")} | {
                "created_at": row.created_at.isoformat() if row.created_at else None}


def list_identifiers(session, organization_id):
    return [serialize(row) for row in session.scalars(select(OrganizationIdentifier).where(
        OrganizationIdentifier.organization_id == organization_id).order_by(OrganizationIdentifier.id))]


def find_owner(session, data):
    """The organization that already holds the number described by ``data``, or None."""
    country, kind, value = normalize_identifier(*(data.get(k) for k in ("country_code", "identifier_type", "value")))
    return session.scalar(select(Organization).join(OrganizationIdentifier).where(
        OrganizationIdentifier.country_code == country, OrganizationIdentifier.identifier_type == kind,
        OrganizationIdentifier.value == value))


def add_identifier(session, organization_id, data):
    if not isinstance(data, dict):
        raise IdentifierError("body")
    country, kind, value = normalize_identifier(*(data.get(k) for k in ("country_code", "identifier_type", "value")))
    optional = {}
    for key in ("source_url", "note"):
        text = data.get(key)
        if text is not None and not isinstance(text, str):
            raise IdentifierError("optional_text")
        optional[key] = text.strip() or None if text else None
    if optional["source_url"]:
        url = urlsplit(optional["source_url"])
        if url.scheme not in ("http", "https") or not url.hostname or url.username or url.password:
            raise IdentifierError("source_url")
    query = select(OrganizationIdentifier).where(
        OrganizationIdentifier.country_code == country, OrganizationIdentifier.identifier_type == kind,
        OrganizationIdentifier.value == value)

    def existing(row):
        if row.organization_id != organization_id:
            raise IdentifierConflict(session.get(Organization, row.organization_id))
        return serialize(row), False

    row = session.scalar(query)
    if row is not None:
        return existing(row)
    try:
        with session.begin_nested():
            row = OrganizationIdentifier(organization_id=organization_id, country_code=country,
                                         identifier_type=kind, value=value, **optional)
            session.add(row)
            session.flush()
    except IntegrityError:
        row = session.scalar(query)
        if row is None:
            raise
        return existing(row)
    return serialize(row), True
