#!/usr/bin/env python3
"""Build/update per-neighbor profiles directly on Contact rows from a WhatsApp
group chat export.

Purpose: a personal social-memory aid (accessibility use case — recalling who
neighbors are and what to talk to them about) built from a WhatsApp group
chat the user is a member of. Two separate layers, deliberately kept apart:

1. PROFILE (persistent, factual) — structured facts (occupation, workplace,
   hobbies, pets, kids-as-a-fact, birthday, trips, recent events, community
   involvement) extracted ONLY from what the person explicitly wrote about
   themselves. No inference, no gossip from other members, nothing sensitive
   (health, conflicts, money). Re-running this script on a newer export
   MERGES new facts into the existing stored profile instead of overwriting
   it — the profile lives in Contact.whatsapp_profile (JSONB), one dict per
   group chat under "groups" (own incremental watermark each) plus a single
   merged "profile"/"suggestions" shared across every group the same contact
   is active in.

2. SMALL TALK SUGGESTIONS (derived, regenerated every run) — built from the
   current profile. This step is explicitly allowed to draw on general/world
   knowledge (e.g. "construction work stalls in hard frost" for a builder) to
   propose conversation starters, but must present them as suggestions
   ("możesz zapytać...") and never invent specific unverifiable claims about
   the person.

Storage note (2026-08-24): earlier versions of this script created a
separate `Document` ("Sąsiad: ..." title, whatsapp://... synthetic URL) per
neighbor. That duplicated the place a person's info had to be looked up in
(Document vs. the private Contact book) — this version writes only to
Contact, matched by phone number (reliable — WhatsApp always knows the
sender's number even when a display name is shown) or, failing that, by
normalized name against the existing contact_categories/contacts book. A
sender with neither a phone match nor a name match gets a brand-new Contact.
The one-off migration of the 97 pre-existing whatsapp:// Documents into
Contact + their deletion is imports/whatsapp_neighbor_profiles_migrate_to_contacts.py.

A sender only visible as a phone number (WhatsApp shows the raw number when
the person has no profile name set) is optionally resolved to a real name via
an exported Google Contacts CSV (`--contacts-csv`) — matched by phone digits,
with a per-community suffix like " - Tuwima Gardens" stripped from the
contact's last name and placeholder "unknown" entries ignored.

Usage:
    cd backend
    python imports/whatsapp_neighbor_profiles.py --export "path/to/chat.txt"                       # dry-run preview
    python imports/whatsapp_neighbor_profiles.py --export "..." --sender "ANETA ANTKOWICZ" -v       # single person
    python imports/whatsapp_neighbor_profiles.py --export "..." --apply                             # create/update contacts
    python imports/whatsapp_neighbor_profiles.py --export "..." --owners-csv "TG_składka_05_06.csv" --apply
    python imports/whatsapp_neighbor_profiles.py --export "..." --contacts-csv "contacts.csv" --apply
"""

import argparse
import json
import logging
import os
import re
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from library.whatsapp_parser import (  # noqa: E402
    find_or_create_contact,
    is_noise,
    is_phone_number,
    load_contact_name_index,
    load_contact_phone_index,
    load_contacts,
    message_datetime as _message_datetime,
    normalize_name,
    parse_export,
    parse_meta_timestamp as _parse_meta_timestamp,
    resolve_phone_sender,
)

logger = logging.getLogger("whatsapp_neighbor_profiles")

DEFAULT_MODEL = "Bielik-11B-v3.0-Instruct"

_PROFILE_SHAPE = """{
  "zawod_lub_branza": {"wartosc": "...", "zrodlo": "DD.MM.RRRR, GG:MM"} albo null,
  "miejsce_pracy": {"wartosc": "...", "zrodlo": "DD.MM.RRRR, GG:MM"} albo null,
  "hobby_zainteresowania": [{"wartosc": "...", "zrodlo": "DD.MM.RRRR, GG:MM"}],
  "zwierzeta": [{"wartosc": "...", "zrodlo": "DD.MM.RRRR, GG:MM"}],
  "dzieci": {"wartosc": "...", "zrodlo": "DD.MM.RRRR, GG:MM"} albo null,
  "urodziny": {"wartosc": "DD.MM", "zrodlo": "DD.MM.RRRR, GG:MM"} albo null,
  "podroze_wakacje": [{"gdzie": "...", "kiedy": "...", "zrodlo": "DD.MM.RRRR, GG:MM"}],
  "wydarzenia_ostatnie": [{"co": "...", "kiedy": "...", "zrodlo": "DD.MM.RRRR, GG:MM"}],
  "zaangazowanie_osiedlowe": {"wartosc": "...", "zrodlo": "DD.MM.RRRR, GG:MM"} albo null
}"""

# NOTE: deliberately NOT using ai_ask's response_format (json_schema / grammar-constrained
# decoding) here — verified empirically that combined with a system prompt like this and a
# long per-person corpus, it makes Bielik-11B-v3.0-Instruct degenerate into an endless run
# of blank lines right after the free-text fields, burning the whole token budget without
# ever closing the JSON object. A plain "reply with this JSON shape" instruction does not
# trigger it and reliably returns a small, complete object.
_EXTRACT_JSON_HINT = f"Odpowiedz WYŁĄCZNIE jednym obiektem JSON (bez markdown, bez komentarzy), dokładnie w tym kształcie:\n{_PROFILE_SHAPE}"

_EXTRACT_SYSTEM_PROMPT = """Budujesz i aktualizujesz trwały, faktograficzny profil sąsiada ze wspólnoty \
mieszkaniowej, dla osoby w spektrum autyzmu, która ma problem z zapamiętywaniem ludzi. Dostajesz \
DOTYCHCZASOWY profil tej osoby (może być pusty) oraz NOWE wiadomości, które ta jedna osoba sama \
napisała na czacie grupowym sąsiadów.

Zasady:
- Wypisuj TYLKO fakty, które ta osoba sama jawnie napisała O SOBIE: zawód/branża, miejsce pracy, \
hobby, zwierzęta domowe, dzieci (w tym etap życia jeśli sama go podała, np. "ma dzieci - studenci", \
"małe dzieci" — ale NIGDY dokładny wiek w latach ani imiona), urodziny (tylko jeśli wprost podała \
datę), wyjazdy/wakacje (gdzie, w przybliżeniu kiedy), inne niedawne wydarzenia życiowe, zaangażowanie \
w sprawy wspólnoty. Nigdy nie zgaduj i nie wymyślaj informacji, których nie ma wprost w tekście.
- ZANIM zapiszesz fakt, sprawdź czy wiadomość WPROST mówi to o TEJ KONKRETNEJ osobie jako fakt o \
niej samej — a nie tylko wspomina powiązane słowo przy innej okazji. Samo pojawienie się słowa \
"dziecko"/"dzieci" NIE znaczy, że osoba ma dzieci — to może być nazwa święta ("Dzień Dziecka"), \
cudze dzieci, akcja charytatywna, ogólna dyskusja albo żart. Analogicznie dla innych pól: wzmianka \
o np. "urlopie" w rozmowie o kimś innym, cytat, czy pytanie zadane innej osobie NIE są faktem o \
autorze wiadomości. W razie wątpliwości pomiń fakt zamiast zgadywać.
- Pomijaj całkowicie: sprawy zdrowotne, konflikty i spory między sąsiadami, kwestie finansowe/pieniężne \
konkretnych osób, imiona/dokładny wiek dzieci, wszystko co brzmi jak plotka lub prywatna sprawa. To \
ma być neutralny profil do miłej rozmowy, a nie dossier.
- KAŻDY fakt (każde pole i każdy element listy) ma własne "zrodlo": dokładna data i godzina TEJ \
konkretnej wiadomości, z której ten fakt pochodzi, w formacie widocznym przy wiadomości źródłowej \
(np. "17.11.2024, 20:15"). Jeśli fakt wynika z kilku wiadomości, podaj datę/godzinę najbardziej \
reprezentatywnej z nich. To pozwala później zweryfikować fakt w historii czatu.
- SCAL z dotychczasowym profilem: zachowaj stare fakty razem z ich "zrodlo", które nadal są aktualne, \
dopisz nowe, zaktualizuj wartość I zrodlo jeśli nowe wiadomości je uszczegóławiają lub zmieniają \
(np. zmiana pracy) — nie kasuj starych faktów bez wyraźnego powodu w nowych wiadomościach.
- Listy (hobby_zainteresowania, zwierzeta, podroze_wakacje, wydarzenia_ostatnie) trzymaj krótkie \
(maks. kilka pozycji) — usuwaj z wydarzenia_ostatnie te, które wyraźnie już nieaktualne/bardzo stare, \
jeśli lista robi się długa.
- Pisz po polsku, krótko i konkretnie.
Odpowiadaj WYŁĄCZNIE poprawnym JSON-em zgodnym z podanym kształtem."""

_SUGGEST_JSON_HINT = 'Odpowiedz WYŁĄCZNIE jednym obiektem JSON: {"sugestie": ["...", ...]}'

_SUGGEST_SYSTEM_PROMPT = """Na podstawie profilu sąsiada proponujesz osobie w spektrum autyzmu 2-5 \
konkretnych pomysłów na small talk (żeby wiedziała o co zapytać zamiast ignorować sąsiada). Możesz \
korzystać z ogólnej wiedzy o świecie (np. typowe wyzwania w danym zawodzie, sezonowość, ogólne \
ciekawostki związane z miejscem wyjazdu) żeby dopowiedzieć kontekst — ale WYRAŹNIE odróżniaj to od \
faktów o tej konkretnej osobie. Formułuj sugestie jako pytania/tematy do poruszenia ("Możesz zapytać \
czy..."), nie jako stwierdzenia o osobie. Nie wymyślaj konkretnych zdarzeń, dat czy szczegółów, \
których nie ma w profilu — ogólny kontekst branżowy/sezonowy tak, ale nie fabrykuj faktów o osobie.
Jeśli profil jest zbyt ubogi żeby cokolwiek sensownie zaproponować, zwróć pustą listę.
Odpowiadaj WYŁĄCZNIE poprawnym JSON-em zgodnym z podanym kształtem."""


def group_by_sender(messages: list[dict]) -> dict[str, list[dict]]:
    by_sender: dict[str, list[dict]] = {}
    for msg in messages:
        by_sender.setdefault(msg["sender"], []).append(msg)
    return by_sender


def chunk_messages(msgs: list[dict], chunk_size: int) -> list[list[dict]]:
    """Split a person's full (non-noise) chronological history into fixed-size chunks.

    Chunking + folding the profile forward chunk-by-chunk (via
    extract_or_update_profile's merge semantics) lets the whole history be
    covered without blowing the LLM's context window on the heaviest posters
    — and, unlike a recency-capped single call, it doesn't let a currently
    dominant topic (e.g. an ongoing crisis) crowd out older personal facts.
    """
    real = [m for m in msgs if not is_noise(m["content"])]
    if not real:
        return []
    return [real[i:i + chunk_size] for i in range(0, len(real), chunk_size)]


def messages_to_corpus_text(chunk: list[dict]) -> str:
    return "\n".join(f"{m['date_str']}, {m['time']}: {m['content']}" for m in chunk)


def load_owners(csv_path: str) -> dict[str, list[str]]:
    """Load apartment ownership data.

    Returns dict: normalized-name-token-key (joined, sorted) -> list of
    'Budynek X, piętro Y, mieszkanie Z' strings, keyed by every owner name
    found in the 'I nabywca' / 'II/III nabywca' columns.
    """
    import csv

    owners: dict[str, list[str]] = {}
    with open(csv_path, "r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            apt = f"Budynek {row.get('Budynek', '').strip()}, piętro {row.get('Piętro', '').strip()}, mieszkanie {row.get('Numer mieszkania', '').strip()}"
            for col in ("I nabywca", "II/III nabywca"):
                name = (row.get(col) or "").strip()
                if not name:
                    continue
                tokens = normalize_name(name)
                if not tokens:
                    continue
                key = " ".join(sorted(tokens))
                owners.setdefault(key, []).append(apt)
    return owners


def match_owner(sender_name: str, owners: dict[str, list[str]]) -> list[str] | None:
    sender_tokens = normalize_name(sender_name)
    if not sender_tokens:
        return None
    best = None
    for key, apts in owners.items():
        owner_tokens = set(key.split(" "))
        if sender_tokens.issubset(owner_tokens) or owner_tokens.issubset(sender_tokens):
            if best is None:
                best = apts
            else:
                return None  # ambiguous match, skip
    return best


def _call_llm_json(query: str, system_prompt: str, model: str, label: str, max_token_count: int = 1200) -> dict | None:
    from library.ai import ai_ask

    for attempt in (1, 2):
        try:
            response = ai_ask(
                query,
                model=model,
                temperature=0.4,
                max_token_count=max_token_count,
                system_prompt=system_prompt,
                operation="whatsapp_neighbor_profile",
            )
        except Exception as exc:
            logger.warning("LLM call failed for %s (attempt %d): %s", label, attempt, exc)
            continue
        raw = (response.response_text or "").strip()
        fence = re.match(r"^```(?:json)?\s*(.*?)\s*```$", raw, re.DOTALL)
        if fence:
            raw = fence.group(1)
        try:
            payload = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            logger.warning("Could not parse LLM JSON for %s (attempt %d)", label, attempt)
            continue
        if isinstance(payload, dict):
            return payload
    return None


_PLACEHOLDER_EXACT = {
    "-", "n/a", "nie dotyczy", "brak", "brak danych", "nieznany", "nieznana",
    "nie wiadomo", "nieokreślony", "nieokreslony",
}
# Prefixes catch longer variants the LLM writes instead of null, e.g.
# "nie podano szczegółów", "brak bezpośrednich wzmianek" — a plain exact-match
# set missed these and let them leak into rendered profiles as fake facts.
_PLACEHOLDER_PREFIXES = (
    "nie podano", "brak bezpośrednich", "brak bezposrednich", "brak informacji",
    "brak danych", "brak wzmianek", "nie okreslono", "nieokreslono", "brak konkretnych",
)

SCALAR_FACT_FIELDS = ("zawod_lub_branza", "miejsce_pracy", "dzieci", "urodziny", "zaangazowanie_osiedlowe")
SIMPLE_LIST_FIELDS = ("hobby_zainteresowania", "zwierzeta")  # items: {"wartosc", "zrodlo"}
DATED_LIST_FIELDS = {  # field -> primary text key; items: {<key>, "kiedy", "zrodlo"}
    "podroze_wakacje": "gdzie",
    "wydarzenia_ostatnie": "co",
}
ALL_PROFILE_FIELDS = SCALAR_FACT_FIELDS + SIMPLE_LIST_FIELDS + tuple(DATED_LIST_FIELDS)


def _is_placeholder(v) -> bool:
    if not isinstance(v, str):
        return False
    s = v.strip().lower()
    return s in _PLACEHOLDER_EXACT or s.startswith(_PLACEHOLDER_PREFIXES)


def _drop_placeholder_zrodlo(item: dict) -> dict:
    if _is_placeholder(item.get("zrodlo")):
        item = {**item, "zrodlo": None}
    return item


def _clean_profile(profile: dict) -> dict:
    """Null out placeholder "not stated" values and drop malformed/empty sourced facts.

    Every fact is expected as {"wartosc"/"co"/"gdzie": str, "zrodlo": str} (scalar
    fields) or a list of such dicts — see _PROFILE_SHAPE. Tolerates the LLM
    occasionally returning a bare string instead of the {value, zrodlo} shape.
    """
    cleaned = {}
    for field in SCALAR_FACT_FIELDS:
        v = profile.get(field)
        if isinstance(v, str):
            v = None if _is_placeholder(v) else {"wartosc": v, "zrodlo": None}
        elif isinstance(v, dict):
            if not v.get("wartosc") or _is_placeholder(v.get("wartosc")):
                v = None
            else:
                v = _drop_placeholder_zrodlo(v)
        else:
            v = None
        cleaned[field] = v

    for field in SIMPLE_LIST_FIELDS:
        items = profile.get(field)
        result = []
        if isinstance(items, list):
            for item in items:
                if isinstance(item, str) and not _is_placeholder(item):
                    result.append({"wartosc": item, "zrodlo": None})
                elif isinstance(item, dict) and item.get("wartosc") and not _is_placeholder(item.get("wartosc")):
                    result.append(_drop_placeholder_zrodlo(item))
        cleaned[field] = result

    for field, key in DATED_LIST_FIELDS.items():
        items = profile.get(field)
        result = []
        if isinstance(items, list):
            for item in items:
                if isinstance(item, dict) and item.get(key) and not _is_placeholder(item.get(key)):
                    result.append(_drop_placeholder_zrodlo(item))
        cleaned[field] = result

    return cleaned


def _strip_sources(profile: dict) -> dict:
    """Drop 'zrodlo' citations before feeding the profile into the small-talk step."""
    def strip_item(item):
        if isinstance(item, dict):
            return {k: v for k, v in item.items() if k != "zrodlo"}
        return item

    out = {}
    for field in SCALAR_FACT_FIELDS:
        v = profile.get(field)
        out[field] = strip_item(v) if v else None
    for field in SIMPLE_LIST_FIELDS + tuple(DATED_LIST_FIELDS):
        out[field] = [strip_item(i) for i in (profile.get(field) or [])]
    return out


def extract_or_update_profile(sender_name: str, corpus_text: str, existing_profile: dict | None, model: str) -> dict | None:
    """Merge facts from new messages into the existing stored profile (LLM call 1)."""
    if not corpus_text.strip():
        return existing_profile
    existing_json = json.dumps(existing_profile, ensure_ascii=False) if existing_profile else "{}"
    query = (
        f"Dotychczasowy profil tej osoby (JSON, może być pusty):\n{existing_json}\n\n"
        f"Nowe wiadomości od „{sender_name}” na czacie sąsiedzkim:\n\n{corpus_text}\n\n{_EXTRACT_JSON_HINT}"
    )
    payload = _call_llm_json(query, _EXTRACT_SYSTEM_PROMPT, model, sender_name)
    return _clean_profile(payload) if payload is not None else existing_profile


def generate_small_talk(sender_name: str, profile: dict | None, model: str) -> list[str]:
    """Derive fresh conversation-starter suggestions from the current profile (LLM call 2)."""
    if not profile or not any(profile.get(k) for k in ALL_PROFILE_FIELDS):
        return []
    query = f"Profil sąsiada „{sender_name}”:\n{json.dumps(_strip_sources(profile), ensure_ascii=False)}\n\n{_SUGGEST_JSON_HINT}"
    payload = _call_llm_json(query, _SUGGEST_SYSTEM_PROMPT, model, f"{sender_name} (sugestie)", max_token_count=700)
    if not payload:
        return []
    suggestions = payload.get("sugestie")
    return suggestions if isinstance(suggestions, list) else []


def format_profile_preview(display_name: str, stats: dict, apartments: list[str] | None, profile: dict | None,
                            suggestions: list[str], phone: str | None = None) -> str:
    """Human-readable dry-run preview of what would be written to Contact.whatsapp_profile."""
    lines = [f"# Sąsiad: {display_name}", ""]
    if apartments:
        lines.append("Mieszkanie: " + "; ".join(apartments))
    if phone:
        lines.append(f"Telefon: {phone}")
    lines.append(f"Wiadomości w grupie: {stats['message_count']} (od {stats['first_date']} do {stats['last_date']})")
    lines.append("")

    has_facts = profile and any(profile.get(k) for k in ALL_PROFILE_FIELDS)
    if not has_facts:
        lines.append("(za mało treściwych wiadomości, żeby zbudować profil tej osoby)")
        return "\n".join(lines)

    def cite(zrodlo: str | None) -> str:
        return f" (źródło: {zrodlo})" if zrodlo else ""

    zawod, miejsce = profile.get("zawod_lub_branza"), profile.get("miejsce_pracy")
    if zawod or miejsce:
        bits = [f.get("wartosc", "") for f in (zawod, miejsce) if f]
        lines.append("Czym się zajmuje: " + " — ".join(bits) + cite((zawod or miejsce).get("zrodlo")))
    for t in profile.get("hobby_zainteresowania") or []:
        lines.append(f"Hobby: {t.get('wartosc', '')}" + cite(t.get("zrodlo")))
    for z in profile.get("zwierzeta") or []:
        lines.append(f"Zwierzę: {z.get('wartosc', '')}" + cite(z.get("zrodlo")))
    if profile.get("dzieci"):
        lines.append("Rodzina: " + profile["dzieci"].get("wartosc", "") + cite(profile["dzieci"].get("zrodlo")))
    if profile.get("urodziny"):
        u = profile["urodziny"]
        lines.append(f"Urodziny: {u.get('wartosc', '')}" + cite(u.get("zrodlo")))
    for p in profile.get("podroze_wakacje") or []:
        gdzie, kiedy = p.get("gdzie", ""), p.get("kiedy", "")
        lines.append(f"Podróż: {gdzie}" + (f" ({kiedy})" if kiedy else "") + cite(p.get("zrodlo")))
    for e in profile.get("wydarzenia_ostatnie") or []:
        co, kiedy = e.get("co", ""), e.get("kiedy", "")
        lines.append(f"Wydarzenie: {co}" + (f" ({kiedy})" if kiedy else "") + cite(e.get("zrodlo")))
    if profile.get("zaangazowanie_osiedlowe"):
        z = profile["zaangazowanie_osiedlowe"]
        lines.append("Zaangażowanie osiedlowe: " + z.get("wartosc", "") + cite(z.get("zrodlo")))
    if suggestions:
        lines.append("Pomysły na rozmowę:")
        for s in suggestions:
            lines.append(f"  - {s}")
    return "\n".join(lines)


def update_whatsapp_profile(contact, group_slug: str, group_label: str, profile: dict | None,
                             suggestions: list[str], stats: dict, new_last_processed_at: str) -> None:
    state = dict(contact.whatsapp_profile or {})
    state["profile"] = profile or {}
    state["suggestions"] = suggestions
    groups = dict(state.get("groups") or {})
    groups[group_slug] = {
        "group_label": group_label,
        "last_processed_at": new_last_processed_at,
        "message_count": stats["message_count"],
        "first_date": stats["first_date"],
        "last_date": stats["last_date"],
    }
    state["groups"] = groups
    contact.whatsapp_profile = state


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--export", required=True, help="Ścieżka do wyeksportowanego pliku .txt czatu WhatsApp")
    parser.add_argument("--owners-csv", default=None, help="Opcjonalny CSV właścicieli mieszkań")
    parser.add_argument("--contacts-csv", default=None, help="Opcjonalny eksport Kontaktów Google (CSV) do rozwiązywania nadawców widocznych jako numer telefonu")
    parser.add_argument("--contacts-suffix", default="Tuwima Gardens", help="Sufiks do usunięcia z nazwiska w --contacts-csv, np. ' - Tuwima Gardens'")
    parser.add_argument("--group-label", default="Tuwima Gardens - Czat ogólny", help="Etykieta grupy czatu (zapisywana w profilu)")
    parser.add_argument("--group-slug", default="tuwima-gardens/czat-ogolny", help="Identyfikator grupy czatu (klucz watermarku w whatsapp_profile.groups)")
    parser.add_argument("--contact-group", default="Tuwima Gardens Mieszkańcy", help="Grupa kontaktów (contact_groups), do której trafiają dopasowani/nowi sąsiedzi")
    parser.add_argument("--source", default="own")
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--min-messages", type=int, default=5, help="Pomiń nadawców z mniejszą liczbą treściwych wiadomości")
    parser.add_argument("--chunk-size", type=int, default=150, help="Wiadomości na jedno wywołanie LLM (cała historia jest dzielona na takie porcje, chronologicznie)")
    parser.add_argument("--sender", default=None, help="Przetwórz tylko wskazanych nadawców, po przecinku (dopasowanie dokładne)")
    parser.add_argument("--limit", type=int, default=None, help="Maks. liczba osób do przetworzenia (testy)")
    parser.add_argument("--force", action="store_true", help="Zignoruj zapisany profil/znacznik czasu i przetwórz całą historię od nowa (np. po poprawce promptu)")
    parser.add_argument("--apply", action="store_true", help="Zapisz/zaktualizuj kontakty w bazie (domyślnie: tylko podgląd)")
    parser.add_argument("--skip-llm", action="store_true", help="Tylko parsowanie/statystyki, bez wywołań LLM (do testów parsera)")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO, format="%(levelname)s %(message)s")

    messages = parse_export(args.export)
    logger.info("Sparsowano %d wiadomości z eksportu.", len(messages))
    by_sender = group_by_sender(messages)
    logger.info("Unikalnych nadawców: %d", len(by_sender))

    owners = load_owners(args.owners_csv) if args.owners_csv else {}
    contacts_csv = load_contacts(args.contacts_csv, args.contacts_suffix) if args.contacts_csv else {}
    if contacts_csv:
        logger.info("Wczytano %d numerów telefonów z %s", len(contacts_csv), args.contacts_csv)

    senders = sorted(by_sender.keys(), key=lambda s: -len(by_sender[s]))
    if args.sender:
        wanted = {s.strip() for s in args.sender.split(",")}
        senders = [s for s in senders if s in wanted]
    if args.limit:
        senders = senders[: args.limit]

    session = None
    default_category_id = None
    contact_group = None
    phone_index: dict[str, int] = {}
    name_index: dict[str, int] = {}
    if args.apply:
        from sqlalchemy import select

        from library.contact_change_log import record_contact_change
        from library.db.engine import get_session
        from library.db.models import ContactCategory, ContactGroup

        session = get_session()
        default_category = session.execute(
            select(ContactCategory).where(ContactCategory.name == "Osoba prywatna")
        ).scalars().first()
        if default_category is None:
            logger.error("Brak kategorii 'Osoba prywatna' w contact_categories — przerywam")
            session.close()
            return
        default_category_id = default_category.id

        contact_group = session.execute(
            select(ContactGroup).where(ContactGroup.name == args.contact_group)
        ).scalars().first()
        if contact_group is None:
            contact_group = ContactGroup(name=args.contact_group)
            session.add(contact_group)
            session.flush()

        phone_index = load_contact_phone_index(session)
        name_index = load_contact_name_index(session)

    created, updated, skipped_short, skipped_no_data, skipped_no_new = 0, 0, 0, 0, 0

    for sender in senders:
        msgs = by_sender[sender]
        real_msgs = [m for m in msgs if not is_noise(m["content"])]
        if len(real_msgs) < args.min_messages:
            skipped_short += 1
            logger.debug("Pomijam %s: tylko %d treściwych wiadomości", sender, len(real_msgs))
            continue

        resolved_name = resolve_phone_sender(sender, contacts_csv) if contacts_csv and is_phone_number(sender) else None
        display_name = resolved_name or sender
        phone_for_content = sender if is_phone_number(sender) else None
        apartments = match_owner(display_name, owners) if owners and not is_phone_number(display_name) else None

        contact = None
        contact_is_new = False
        existing_profile = None
        last_processed_at = None
        if args.apply:
            contact, contact_is_new = find_or_create_contact(session, display_name, phone_for_content,
                                                               default_category_id, phone_index, name_index)
            if contact_group not in contact.groups:
                contact.groups.append(contact_group)
            if not args.force:
                group_state = ((contact.whatsapp_profile or {}).get("groups") or {}).get(args.group_slug)
                if group_state:
                    existing_profile = (contact.whatsapp_profile or {}).get("profile")
                    last_processed_at = group_state.get("last_processed_at")

        # Incremental import: only feed messages newer than the stored watermark into the
        # LLM — the merge in extract_or_update_profile means older facts aren't lost, this
        # just avoids re-paying for (and re-calling the LLM on) history already folded in.
        last_dt = _parse_meta_timestamp(last_processed_at)
        if last_dt is not None:
            new_msgs = [m for m in msgs if (_message_datetime(m) or datetime.max) > last_dt]
        else:
            new_msgs = msgs

        if last_dt is not None and not new_msgs:
            skipped_no_new += 1
            logger.debug("Pomijam %s: brak nowych wiadomości od %s", sender, last_processed_at)
            continue

        chunks = chunk_messages(new_msgs, args.chunk_size)
        stats = {
            "message_count": len(msgs),
            "first_date": msgs[0]["date_str"],
            "last_date": msgs[-1]["date_str"],
        }

        logger.info("Analizuję: %s (%d wiadomości razem, %d nowych, %d porcji po %d)%s%s", display_name, len(msgs),
                    len(new_msgs), len(chunks), args.chunk_size, f" — {apartments}" if apartments else "",
                    f" [od {last_processed_at}]" if last_dt else "")

        if args.skip_llm:
            profile, suggestions = existing_profile, []
        else:
            profile = existing_profile
            for i, chunk in enumerate(chunks, 1):
                logger.debug("  porcja %d/%d (%d wiadomości)", i, len(chunks), len(chunk))
                profile = extract_or_update_profile(display_name, messages_to_corpus_text(chunk), profile, args.model)
            suggestions = generate_small_talk(display_name, profile, args.model)
        if not profile:
            skipped_no_data += 1

        new_last_processed_at = f"{msgs[-1]['date_str']}, {msgs[-1]['time']}"

        if not args.apply:
            preview = format_profile_preview(display_name, stats, apartments, profile, suggestions, phone_for_content)
            print("=" * 70)
            print("[DRY-RUN]")
            print(preview)
            continue

        update_whatsapp_profile(contact, args.group_slug, args.group_label, profile, suggestions, stats, new_last_processed_at)
        changed_fields = ["whatsapp_profile"]
        if contact_is_new:
            changed_fields += ["first_name", "last_name", "category_id"]
        record_contact_change(
            session, contact, "whatsapp_analysis", changed_fields=changed_fields,
            note=f"Analiza czatu WhatsApp „{args.group_label}” ({stats['message_count']} wiadomości)",
        )
        session.commit()
        if contact_is_new:
            created += 1
            logger.info("Utworzono kontakt #%d: %s", contact.id, display_name)
        else:
            updated += 1
            logger.info("Zaktualizowano kontakt #%d: %s", contact.id, display_name)

    if session:
        session.close()

    print()
    print(f"Nadawców przetworzonych: {len(senders)}")
    print(f"Utworzono nowych kontaktów: {created}")
    print(f"Zaktualizowano istniejących kontaktów: {updated}")
    print(f"Pominięto (za mało wiadomości): {skipped_short}")
    print(f"Pominięto (brak nowych wiadomości od ostatniego importu): {skipped_no_new}")
    print(f"Bez profilu / bez danych: {skipped_no_data}")


if __name__ == "__main__":
    main()
