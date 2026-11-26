"""Transient comparison of public CRBR filings and KRS shareholder history."""

import logging
import re
import unicodedata
from datetime import datetime, timezone

from library import company_registry_client as client

logger = logging.getLogger(__name__)


def normalize_krs(value):
    if not isinstance(value, str) or not re.fullmatch(r"[0-9]{1,10}", value.strip()):
        raise ValueError("KRS musi zawierać od 1 do 10 cyfr.")
    return value.strip().zfill(10)


def normalize_nip(value):
    if not isinstance(value, str):
        raise ValueError("Nieprawidłowy NIP.")
    value = re.sub(r"[\s.-]", "", value.upper().strip())
    value = value.removeprefix("PL")
    if not re.fullmatch(r"[0-9]{10}", value) or sum(int(n) * w for n, w in zip(value, (6, 5, 7, 2, 3, 4, 5, 6, 7))) % 11 != int(value[-1]):
        raise ValueError("NIP musi zawierać 10 cyfr i poprawną sumę kontrolną.")
    return value


def normalize_name(value):
    value = unicodedata.normalize("NFKD", value.casefold().replace("ł", "l"))
    value = "".join(c for c in value if not unicodedata.combining(c))
    value = re.sub(r"[^a-z0-9]+", " ", value)
    value = re.sub(r"\b(spolka z ograniczona odpowiedzialnoscia|sp z o o|spolka akcyjna|s a|spolka komandytowa|sp k)\b", " ", value)
    return " ".join(value.split())


def _warnings(filings, krs):
    current = [f for f in filings if f["is_current"]]
    warnings = []
    shareholders = krs.get("current_shareholders", []) + krs.get("former_shareholders", [])
    if any(f["presented_from"] and row.get(f"{kind}_entry", 0) not in (None, 0, 1)
           and not row.get(f"{kind}_by_correction")
           and row.get(f"{kind}_at") and row[f"{kind}_at"] > f["presented_from"][:10]
           for f in current for row in shareholders for kind in ("added", "removed")):
        warnings.append({"code": "krs_shareholders_changed_after_filing", "message":
                         "Po początku prezentacji aktualnego zgłoszenia CRBR zmienili się wspólnicy w KRS; wpis może być nieaktualny. Warto porównać dokumenty źródłowe."})
    texts = [normalize_name(o["text"]) for f in current for b in f["beneficiaries"]
             for o in b["ownership"] if o["kind"] in ("direct", "indirect")]
    if any(row["is_company"] and normalize_name(row["name"])
           and any(f" {normalize_name(row['name'])} " in f" {text} " for text in texts)
           for row in krs.get("former_shareholders", [])):
        warnings.append({"code": "crbr_mentions_former_shareholder", "message":
                         "Aktualny CRBR wymienia spółkę wykreśloną z listy wspólników KRS; wpis może być nieaktualny. To wskazówka do weryfikacji, nie ocena prawna."})
    return warnings


def check_company(nip=None, krs=None):
    if (nip is None) == (krs is None):
        raise ValueError("Podaj dokładnie jeden identyfikator: NIP albo KRS.")
    nip = normalize_nip(nip) if nip is not None else None
    krs = normalize_krs(krs) if krs is not None else None
    result = {"query": {"nip": nip, "krs": krs}, "checked_at": datetime.now(timezone.utc).isoformat(),
              "warnings": [], "source_urls": {"crbr": client.CRBR_URL, "krs": client.KRS_URL}}
    try:
        filings = client.get_crbr(nip=nip, krs=krs)
        result["crbr"] = {"status": "ok" if filings else "not_found", "message":
                          "Pobrano zgłoszenia CRBR." if filings else "Brak informacji w CRBR.", "filings": filings}
    except Exception as exc:
        # Exception text can contain remote response data: log the type only.
        logger.warning("CRBR lookup failed: %s", type(exc).__name__)
        result["crbr"] = {"status": "error", "message": "Nie udało się pobrać lub odczytać CRBR.", "filings": []}
    if krs is None:
        candidates = {f["krs"] for f in result["crbr"]["filings"] if f["is_current"] and f["krs"]}
        if len(candidates) == 1:
            try:
                krs = normalize_krs(candidates.pop())
            except ValueError:
                pass
    if krs is None:
        result["krs"] = {"status": "skipped", "message": "Brak jednoznacznego KRS w CRBR. API KRS nie wyszukuje po NIP; sprawdź ponownie, podając KRS."}
    else:
        result["source_urls"]["krs"] = f"{client.KRS_URL}/{krs}?rejestr=P&format=json"
        try:
            data = client.get_krs(krs)
            result["krs"] = {"status": "ok" if data else "not_found", "message":
                             "Pobrano KRS. Lista wspólników obejmuje spółki z o.o.; nie obejmuje akcjonariuszy spółek akcyjnych.", **(data or {})}
            if data is None:
                result["krs"]["message"] = "Brak odpisu KRS w rejestrach P i S."
            elif data.get("source_url"):
                result["source_urls"]["krs"] = data["source_url"]
        except Exception as exc:
            logger.warning("KRS lookup failed: %s", type(exc).__name__)
            result["krs"] = {"status": "error", "message": "Nie udało się pobrać lub odczytać KRS."}
    result["warnings"] = _warnings(result["crbr"]["filings"], result["krs"])
    return result
