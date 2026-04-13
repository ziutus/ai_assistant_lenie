#!/usr/bin/env python3
"""Download and query Freedom House 'Freedom in the World' data via Our World in Data API.

Usage:
    cd backend
    python imports/freedom_house_import.py --download                        # Download/update cached data
    python imports/freedom_house_import.py --country "Poland"                # Lookup by English name
    python imports/freedom_house_import.py --country "Korea Północna"        # Lookup by Polish name
    python imports/freedom_house_import.py --country "Poland" --year 2020    # Specific year
    python imports/freedom_house_import.py --country "Poland" --history      # All years
    python imports/freedom_house_import.py --list                            # List all countries
    python imports/freedom_house_import.py --list --status "Not Free"        # Filter by status
    python imports/freedom_house_import.py --markdown "Korea Północna"       # Markdown block for Obsidian
"""

import argparse
import csv
import json
import os
import sys
from typing import Optional
from urllib.request import urlopen, Request
from urllib.error import URLError

CACHE_DIR = os.path.join(os.path.dirname(__file__), "tmp")
CACHE_FILE = os.path.join(CACHE_DIR, "freedom_house.csv")

# OWID indicator IDs for Freedom House data
INDICATORS = {
    "regime":          1210107,  # 0=Not Free, 1=Partly Free, 2=Free
    "polrights":       1210106,  # Political rights rating (1-7, 1=most free)
    "civlibs":         1210105,  # Civil liberties rating (1-7, 1=most free)
    "total_score":     1210111,  # Total score (0-100, from 2002)
    "polrights_score": 1210108,  # Political rights score (0-40, from 2002)
    "civlibs_score":   1210109,  # Civil liberties score (0-60, from 2002)
    "electdem":        1210113,  # Electoral democracy (0/1)
}

REGIME_LABELS = {0: "Not Free", 1: "Partly Free", 2: "Free"}

# Polish → English country name mapping (for Obsidian note names)
PL_TO_EN = {
    "Arabia Saudyjska": "Saudi Arabia",
    "Argentyna": "Argentina",
    "Armenia": "Armenia",
    "Azerbejdżan": "Azerbaijan",
    "Azerbejdzan": "Azerbaijan",
    "Bahrajn": "Bahrain",
    "Bahrain": "Bahrain",
    "Belgia": "Belgium",
    "Białoruś": "Belarus",
    "Chiny": "China",
    "Dania": "Denmark",
    "Dżibuti": "Djibouti",
    "Francja": "France",
    "Hiszpania": "Spain",
    "Holandia": "Netherlands",
    "Indie": "India",
    "Irak": "Iraq",
    "Iran": "Iran",
    "Izrael": "Israel",
    "Japonia": "Japan",
    "Kambodża": "Cambodia",
    "Kambodza": "Cambodia",
    "Katar": "Qatar",
    "Kazachstan": "Kazakhstan",
    "Kenia": "Kenya",
    "Korea Południowa": "South Korea",
    "Korea Północna": "North Korea",
    "Kosowo": "Kosovo",
    "Kuba": "Cuba",
    "Kuwejt": "Kuwait",
    "Litwa": "Lithuania",
    "Malediwy": "Maldives",
    "Mali": "Mali",
    "Maroko": "Morocco",
    "Mauretania": "Mauritania",
    "Mołdawia": "Moldova",
    "Nepal": "Nepal",
    "Niemcy": "Germany",
    "Nigeria": "Nigeria",
    "Oman": "Oman",
    "Pakistan": "Pakistan",
    "Palestyna": "Palestine",
    "Panama": "Panama",
    "Polska": "Poland",
    "Republika Środkowoafrykańska": "Central African Republic",
    "Rosja": "Russia",
    "Rumunia": "Romania",
    "Senegal": "Senegal",
    "Serbia": "Serbia",
    "Stany Zjednoczone": "United States",
    "Sudan": "Sudan",
    "Syria": "Syria",
    "Szwecja": "Sweden",
    "Tajwan": "Taiwan",
    "Tunezja": "Tunisia",
    "Turcja": "Turkey",
    "Uganda": "Uganda",
    "Ukraina": "Ukraine",
    "Wenezuela": "Venezuela",
    "Węgry": "Hungary",
    "Wietnam": "Vietnam",
    "Włochy": "Italy",
    "Algieria": "Algeria",
    "Zjednoczone Emiraty Arabskie": "United Arab Emirates",
}

# Reverse mapping for display
EN_TO_PL = {v: k for k, v in PL_TO_EN.items()}


def _fetch_json(url: str) -> dict:
    """Fetch JSON from URL."""
    req = Request(url, headers={"User-Agent": "lenie-ai-freedom-house/1.0"})
    with urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _fetch_entity_map(indicator_id: int) -> dict:
    """Fetch entity_id → (name, code) mapping from OWID metadata."""
    url = f"https://api.ourworldindata.org/v1/indicators/{indicator_id}.metadata.json"
    meta = _fetch_json(url)
    entity_map = {}
    for dim in meta.get("dimensions", {}).get("entities", {}).get("values", []):
        entity_map[dim["id"]] = (dim.get("name", ""), dim.get("code", ""))
    return entity_map


def download_data():
    """Download all Freedom House indicators from OWID API and save as CSV."""
    os.makedirs(CACHE_DIR, exist_ok=True)

    print("Pobieranie mapowania krajów...")
    first_indicator_id = list(INDICATORS.values())[0]
    entity_map = _fetch_entity_map(first_indicator_id)
    print(f"  Znaleziono {len(entity_map)} krajów/terytoriów")

    # Fetch all indicators
    all_data = {}  # (entity_id, year) → {field: value, ...}
    for field_name, indicator_id in INDICATORS.items():
        print(f"Pobieranie: {field_name} (indicator {indicator_id})...")
        url = f"https://api.ourworldindata.org/v1/indicators/{indicator_id}.data.json"
        data = _fetch_json(url)

        values = data.get("values", [])
        years = data.get("years", [])
        entities = data.get("entities", [])

        for val, year, eid in zip(values, years, entities):
            key = (eid, year)
            if key not in all_data:
                all_data[key] = {}
            all_data[key][field_name] = val

        print(f"  {len(values)} rekordów")

    # Write CSV
    fieldnames = ["country", "code", "year", "regime", "status",
                  "polrights", "civlibs", "total_score", "polrights_score",
                  "civlibs_score", "electdem"]

    rows = []
    for (eid, year), fields in sorted(all_data.items(), key=lambda x: (x[0][0], x[0][1])):
        name, code = entity_map.get(eid, ("Unknown", ""))
        regime = fields.get("regime")
        row = {
            "country": name,
            "code": code,
            "year": year,
            "regime": regime if regime is not None else "",
            "status": REGIME_LABELS.get(regime, "") if regime is not None else "",
            "polrights": fields.get("polrights", ""),
            "civlibs": fields.get("civlibs", ""),
            "total_score": fields.get("total_score", ""),
            "polrights_score": fields.get("polrights_score", ""),
            "civlibs_score": fields.get("civlibs_score", ""),
            "electdem": fields.get("electdem", ""),
        }
        rows.append(row)

    with open(CACHE_FILE, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    # Stats
    latest_year = max(r["year"] for r in rows)
    latest_rows = [r for r in rows if r["year"] == latest_year and r["status"]]
    status_counts = {}
    for r in latest_rows:
        status_counts[r["status"]] = status_counts.get(r["status"], 0) + 1

    print(f"\nZapisano {len(rows)} rekordów do {CACHE_FILE}")
    print(f"Ostatni rok: {latest_year}")
    print(f"Rozkład ({latest_year}): {status_counts}")


def _load_data() -> list:
    """Load cached CSV data."""
    if not os.path.exists(CACHE_FILE):
        print(f"Brak pliku cache. Uruchom najpierw: python imports/freedom_house_import.py --download",
              file=sys.stderr)
        sys.exit(1)

    with open(CACHE_FILE, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        return list(reader)


def _resolve_country_name(name: str) -> str:
    """Resolve Polish name to English (OWID) name. Returns original if no mapping."""
    return PL_TO_EN.get(name, name)


def _find_country_rows(data: list, country: str, year: Optional[int] = None) -> list:
    """Find rows for a country (case-insensitive, supports Polish names)."""
    en_name = _resolve_country_name(country)
    matches = [r for r in data if r["country"].lower() == en_name.lower()]
    if not matches:
        # Fuzzy: try substring match
        matches = [r for r in data if en_name.lower() in r["country"].lower()]
    if year:
        matches = [r for r in matches if int(r["year"]) == year]
    return sorted(matches, key=lambda r: int(r["year"]))


def cmd_country(country: str, year: Optional[int] = None, history: bool = False):
    """Show Freedom House data for a country."""
    data = _load_data()
    rows = _find_country_rows(data, country)

    if not rows:
        print(f"Nie znaleziono kraju: {country}")
        en = _resolve_country_name(country)
        if en != country:
            print(f"  (szukano jako: {en})")
        return

    if year:
        rows = [r for r in rows if int(r["year"]) == year]
        if not rows:
            print(f"Brak danych dla {country} w roku {year}")
            return

    if not history:
        # Show only latest year
        rows = [rows[-1]]

    pl_name = EN_TO_PL.get(rows[0]["country"], "")
    header = rows[0]["country"]
    if pl_name:
        header += f" ({pl_name})"

    print(f"\n{header}")
    print("=" * 60)
    print(f"{'Rok':>6}  {'Status':>12}  {'PR':>3}  {'CL':>3}  {'Score':>6}  {'PR_S':>5}  {'CL_S':>5}  {'ElDem':>5}")
    print("-" * 60)

    for r in rows:
        print(f"{r['year']:>6}  {r['status']:>12}  {r['polrights']:>3}  {r['civlibs']:>3}  "
              f"{r['total_score']:>6}  {r['polrights_score']:>5}  {r['civlibs_score']:>5}  {r['electdem']:>5}")

    print()
    print("PR = Political Rights (1-7, 1=best), CL = Civil Liberties (1-7, 1=best)")
    print("Score = Total (0-100), PR_S = PR Score (0-40), CL_S = CL Score (0-60)")
    print("ElDem = Electoral Democracy (0/1)")


def cmd_markdown(country: str, year: Optional[int] = None):
    """Generate markdown block for Obsidian note."""
    data = _load_data()
    rows = _find_country_rows(data, country)

    if not rows:
        print(f"Nie znaleziono kraju: {country}")
        return

    if year:
        rows = [r for r in rows if int(r["year"]) == year]
    else:
        rows = [rows[-1]]  # latest

    r = rows[0]
    yr = r["year"]
    status = r["status"]
    total = r["total_score"]
    pr = r["polrights"]
    cl = r["civlibs"]
    pr_s = r["polrights_score"]
    cl_s = r["civlibs_score"]
    electdem = "Tak" if r["electdem"] == "1" else "Nie"

    print(f"## Freedom House — Freedom in the World {yr}")
    print()
    print(f"- **Status**: {status}")
    print(f"- **Wynik ogólny**: {total}/100")
    print(f"- **Prawa polityczne**: {pr}/7 (wynik: {pr_s}/40)")
    print(f"- **Wolności obywatelskie**: {cl}/7 (wynik: {cl_s}/60)")
    print(f"- **Demokracja wyborcza**: {electdem}")
    print()
    print(f"Źródło: [Freedom House](https://freedomhouse.org/country/{r['country'].lower().replace(' ', '-')}/freedom-world/{yr})")


def cmd_list(status_filter: Optional[str] = None):
    """List all countries with latest year data."""
    data = _load_data()

    # Get latest year per country
    latest = {}
    for r in data:
        country = r["country"]
        yr = int(r["year"])
        if country not in latest or yr > int(latest[country]["year"]):
            latest[country] = r

    rows = sorted(latest.values(), key=lambda r: r["country"])

    if status_filter:
        rows = [r for r in rows if r["status"].lower() == status_filter.lower()]

    print(f"\n{'Kraj':<40} {'Rok':>5} {'Status':>12} {'Score':>6} {'PR':>3} {'CL':>3}")
    print("-" * 75)
    for r in rows:
        print(f"{r['country']:<40} {r['year']:>5} {r['status']:>12} {r['total_score']:>6} "
              f"{r['polrights']:>3} {r['civlibs']:>3}")

    print(f"\nŁącznie: {len(rows)} krajów/terytoriów")


def main():
    parser = argparse.ArgumentParser(
        description="Freedom House 'Freedom in the World' data — download and query")

    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--download", action="store_true", help="Pobierz/zaktualizuj dane z OWID API")
    group.add_argument("--country", type=str, help="Pokaż dane dla kraju (EN lub PL nazwa)")
    group.add_argument("--markdown", type=str, help="Wygeneruj blok markdown dla Obsidian")
    group.add_argument("--list", action="store_true", help="Lista wszystkich krajów")

    parser.add_argument("--year", type=int, default=None, help="Konkretny rok")
    parser.add_argument("--history", action="store_true", help="Pokaż wszystkie lata (z --country)")
    parser.add_argument("--status", type=str, default=None,
                        help="Filtruj po statusie: 'Free', 'Partly Free', 'Not Free' (z --list)")

    args = parser.parse_args()

    try:
        if args.download:
            download_data()
        elif args.country:
            cmd_country(args.country, year=args.year, history=args.history)
        elif args.markdown:
            cmd_markdown(args.markdown, year=args.year)
        elif args.list:
            cmd_list(status_filter=args.status)
    except URLError as e:
        print(f"Błąd połączenia: {e}", file=sys.stderr)
        sys.exit(1)
    except KeyboardInterrupt:
        print("\nPrzerwano.")


if __name__ == "__main__":
    main()
