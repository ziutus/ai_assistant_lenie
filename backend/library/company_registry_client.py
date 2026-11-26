"""Public registry clients. Only explicitly allowlisted, redacted fields escape parsing."""

import re
from datetime import date
from xml.etree.ElementTree import Element, SubElement, tostring

import requests
from defusedxml.ElementTree import fromstring

from library.external_service_events import observed_request

CRBR_NS = "http://www.mf.gov.pl/schematy/AP/ApiPrzegladoweCRBR/2022/12/01"
CRBR_OPERATION_NS = "http://www.mf.gov.pl/uslugiBiznesowe/uslugiESB/AP/ApiPrzegladoweCRBR/2022/12/01"
CRBR_URL = "https://bramka-crbr.mf.gov.pl:5058/uslugiBiznesowe/uslugiESB/AP/ApiPrzegladoweCRBR/2022/12/01"
KRS_URL = "https://api-krs.ms.gov.pl/api/krs/OdpisPelny"
TIMEOUT = (10, 45)


def redact(value):
    return re.sub(r"(?<!\d)\d{11}(?!\d)", "[ukryto]", str(value or ""))


def _text(node, path):
    return redact(node.findtext("/".join(f"{{{CRBR_NS}}}{part}" for part in path.split("/")), "")).strip()


def parse_crbr(xml):
    # forbid_dtd also rejects declarations without entities; no raw XML is logged.
    root = fromstring(xml, forbid_dtd=True, forbid_entities=True, forbid_external=True)
    status = root.findtext(f".//{{{CRBR_NS}}}Status")
    if status == "BrakInformacji":
        return []
    if status != "IstniejaInformacje":
        raise ValueError("Nieprawidłowa odpowiedź CRBR")
    filings = []
    for node in root.findall(f".//{{{CRBR_NS}}}SpolkaIBeneficjenci"):
        beneficiaries = []
        for person in node.findall(f"{{{CRBR_NS}}}ListaBeneficjentowRzeczywistych/{{{CRBR_NS}}}BeneficjentRzeczywisty"):
            ownership = []
            for share in person.findall(f"{{{CRBR_NS}}}ListaInformacjiOUdzialach/{{{CRBR_NS}}}InformacjaOUdzialach"):
                direct = share.find(f"{{{CRBR_NS}}}UprawnieniaWlascicielskieBezposrednie")
                if direct is not None:
                    # Allowlist: never recursively flatten arbitrary XML (PESEL/birth dates).
                    ownership.append({"kind": "direct", "text": "; ".join(filter(None, (
                        _text(direct, field) for field in
                        ("RodzajUprawnienWlascicielskich", "JednostkaMiary", "Ilosc")
                    )))})
                for field, kind in (("UprawnieniaWlascicielskiePosrednie", "indirect"), ("InneUprawnienia", "other")):
                    value = _text(share, field)
                    if value:
                        ownership.append({"kind": kind, "text": value})
            beneficiaries.append({
                "name": " ".join(filter(None, (_text(person, field) for field in
                                              ("PierwszeImie", "KolejneImiona", "Nazwisko")))),
                "group_name": _text(person, "NazwaBeneficjentaGrupowego"),
                "citizenship": _text(person, "Obywatelstwo/Nazwa") or _text(person, "Obywatelstwo/Kod"),
                "residence_country": _text(person, "KrajZamieszkania/Nazwa") or _text(person, "KrajZamieszkania/Kod"),
                "ownership": ownership,
            })
        filings.append({
            "name": _text(node, "Nazwa"), "nip": _text(node, "NIP"), "krs": _text(node, "KRS"),
            "legal_form": _text(node, "OpisFormyOrganizacyjnej"),
            "presented_from": _text(node, "DataPoczatkuPrezentacjiZgloszenia"),
            "presented_to": _text(node, "DataKoncaPrezentacjiZgloszenia"),
            "reference": _text(node, "NumerReferencyjny"), "corrected": _text(node, "Skorygowane"),
            "beneficiaries": beneficiaries,
        })
    latest = max((f["presented_to"] for f in filings), default="")
    for filing in filings:
        filing["is_current"] = bool(latest and filing["presented_to"] == latest)
    return sorted(filings, key=lambda f: (f["presented_from"], f["presented_to"]), reverse=True)


def get_crbr(*, nip=None, krs=None):
    envelope = Element("{http://www.w3.org/2003/05/soap-envelope}Envelope")
    body = SubElement(envelope, "{http://www.w3.org/2003/05/soap-envelope}Body")
    operation = SubElement(body, f"{{{CRBR_OPERATION_NS}}}PobierzInformacjeOSpolkachIBeneficjentach")
    data = SubElement(operation, "PobierzInformacjeOSpolkachIBeneficjentachDane")
    details = SubElement(data, f"{{{CRBR_NS}}}SzczegolyWniosku")
    for key, value in (("NIP" if nip else "KRS", nip or krs), ("DataOd", "2019-10-13"),
                       ("DataDo", date.today().isoformat())):
        SubElement(details, f"{{{CRBR_NS}}}{key}").text = value
    response = observed_request(service="crbr", operation="company_check", request_fn=lambda: requests.post(
        CRBR_URL, data=tostring(envelope, encoding="utf-8", xml_declaration=True),
        headers={"Content-Type": "application/soap+xml; charset=utf-8"}, timeout=TIMEOUT,
    ))
    response.raise_for_status()
    return parse_crbr(response.content)


def _history(item, key):
    values = item.get(key, [])
    return [v for v in values if isinstance(v, dict)] if isinstance(values, list) else []


def _entry(value):
    try:
        return int(value or 0)
    except (ValueError, TypeError):
        return 0


def _active(value):
    return not value.get("nrWpisuWykr")


def _value(item, key, current):
    values = _history(item, key)
    candidates = [v for v in values if _active(v)] if current else values
    value = max(candidates, key=lambda v: _entry(v.get("nrWpisuWprow")), default={}).get(key, "")
    if isinstance(value, dict):
        fields = ("nazwiskoICzlon", "nazwiskoIICzlon") if key == "nazwisko" else ("imie", "imieDrugie")
        value = " ".join(str(value.get(f, "")) for f in fields).strip()
    return redact(value)


def parse_krs(payload):
    odpis = payload["odpis"]
    header = odpis.get("naglowekP") or odpis.get("naglowekS") or {}
    entries, corrections = {}, set()
    for entry in header.get("wpis", []):
        # A correction fixes the register itself; it is not a change of shareholders.
        if str(entry.get("opis", "")).upper().startswith("SPROSTOWANIE"):
            corrections.add(_entry(entry.get("numerWpisu")))
        raw_date = entry.get("dataWpisu", "")
        try:
            day, month, year = raw_date.split(".")
            entries[_entry(entry.get("numerWpisu"))] = date(int(year), int(month), int(day)).isoformat()
        except (ValueError, TypeError):
            continue
    section = odpis["dane"]["dzial1"]
    current, former = [], []
    for item in section.get("wspolnicySpzoo", []):
        names = _history(item, "nazwa") or _history(item, "nazwisko")
        if not names:
            continue
        is_current = any(_active(v) for v in names)
        added = min((_entry(v.get("nrWpisuWprow")) for v in names), default=0)
        removed = max((_entry(v.get("nrWpisuWykr")) for v in names), default=0) if not is_current else 0
        row = {
            "name": _value(item, "nazwa", is_current) or " ".join(filter(None, (
                _value(item, "imiona", is_current), _value(item, "nazwisko", is_current)))),
            "is_company": bool(_history(item, "nazwa")), "krs": _value(item, "krs", is_current),
            "shares": _value(item, "posiadaneUdzialy", is_current),
            "added_entry": added, "added_at": entries.get(added), "added_by_correction": added in corrections,
            "removed_entry": removed or None, "removed_at": entries.get(removed),
            "removed_by_correction": removed in corrections,
        }
        (current if is_current else former).append(row)
    company = section.get("danePodmiotu", {})
    name = _value(company, "nazwa", True) if isinstance(company.get("nazwa"), list) else redact(company.get("nazwa"))
    identifiers = company.get("identyfikatory", {})
    if isinstance(identifiers, list):
        identifiers = max((v for v in identifiers if _active(v)),
                          key=lambda v: _entry(v.get("nrWpisuWprow")), default={})
        identifiers = identifiers.get("identyfikatory", identifiers)
    identifiers = identifiers if isinstance(identifiers, dict) else {}
    numbers = {key: redact(identifiers.get(key)) if isinstance(identifiers.get(key), str) else ""
               for key in ("nip", "regon")}
    # KRS pads a 9-digit REGON to the 14-digit field with zeros.
    if re.fullmatch(r"[0-9]{9}00000", numbers["regon"]):
        numbers["regon"] = numbers["regon"][:9]
    addresses = [v for v in _history(section.get("siedzibaIAdres") or {}, "adres") if _active(v)]
    seat = max(addresses, key=lambda v: _entry(v.get("nrWpisuWprow")), default={})
    address = {target: redact(seat.get(source)) for source, target in (
        ("ulica", "street"), ("nrDomu", "house"), ("nrLokalu", "flat"), ("kodPocztowy", "postal_code"),
        ("miejscowosc", "city"), ("kraj", "country"))}
    return {"name": name, "state_as_of": redact(header.get("stanZDnia")), **numbers,
            "legal_form": _value(company, "formaPrawna", True), "address": address,
            "current_shareholders": current, "former_shareholders": former}


def get_krs(krs):
    for register in ("P", "S"):
        response = observed_request(service="krs", operation="full_extract", request_fn=lambda: requests.get(
            f"{KRS_URL}/{krs}", params={"rejestr": register, "format": "json"}, timeout=TIMEOUT,
        ))
        if response.status_code == 404:
            continue
        response.raise_for_status()
        result = parse_krs(response.json())
        result["krs"] = krs
        result["source_url"] = f"{KRS_URL}/{krs}?rejestr={register}&format=json"
        return result
    return None
