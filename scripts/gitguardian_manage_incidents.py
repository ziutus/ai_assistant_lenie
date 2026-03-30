#!/usr/bin/env python3
"""
GitGuardian Incident Manager

Listuje otwarte incydenty i pozwala je zamykać (resolve/ignore) przez API.

Wymaga zmiennej środowiskowej GITGUARDIAN_API_KEY (lub pliku .env w katalogu projektu).

Użycie:
    python scripts/gitguardian_manage_incidents.py list
    python scripts/gitguardian_manage_incidents.py list --severity high
    python scripts/gitguardian_manage_incidents.py list --repo lenie-server
    python scripts/gitguardian_manage_incidents.py list --severity critical --repo lenie
    python scripts/gitguardian_manage_incidents.py resolve <incident_id> [<incident_id> ...]
    python scripts/gitguardian_manage_incidents.py resolve --all
    python scripts/gitguardian_manage_incidents.py resolve --all --severity high
    python scripts/gitguardian_manage_incidents.py ignore <incident_id> [<incident_id> ...] --reason <reason>
    python scripts/gitguardian_manage_incidents.py ignore --all --reason test_credential
    python scripts/gitguardian_manage_incidents.py ignore --all --severity low --reason low_risk

Powody ignorowania (--reason):
    test_credential, false_positive, low_risk
"""

import argparse
import os
import sys
from pathlib import Path

import requests
from dotenv import load_dotenv

BASE_URL = "https://api.gitguardian.com/v1"
REQUEST_TIMEOUT = 30


def load_api_key() -> str:
    env_path = Path(__file__).resolve().parent.parent / ".env"
    load_dotenv(env_path)

    key = os.environ.get("GITGUARDIAN_API_KEY")
    if key:
        return key

    print("Błąd: Brak GITGUARDIAN_API_KEY (zmienna środowiskowa lub .env)")
    sys.exit(1)


def get_headers(api_key: str) -> dict:
    return {
        "Authorization": f"Token {api_key}",
        "Content-Type": "application/json",
    }


def list_open_incidents(
    api_key: str,
    severity: str | None = None,
    repo: str | None = None,
) -> list[dict]:
    """Pobiera wszystkie otwarte incydenty (TRIGGERED + ASSIGNED).

    Args:
        severity: Filtruj po severity (critical, high, medium, low, info, unknown).
        repo: Filtruj po nazwie repozytorium (substring match, case-insensitive).
              Wymaga dodatkowych zapytań API (pobranie occurrences per incydent).
    """
    incidents = []
    page = 1
    params: dict = {
        "status": "TRIGGERED,ASSIGNED",
        "per_page": 100,
    }
    if severity:
        params["severity"] = severity

    while True:
        params["page"] = page
        resp = requests.get(
            f"{BASE_URL}/incidents/secrets",
            headers=get_headers(api_key),
            params=params,
            timeout=REQUEST_TIMEOUT,
        )
        resp.raise_for_status()
        data = resp.json()
        if not data:
            break
        incidents.extend(data)
        if len(data) < 100:
            break
        page += 1

    if repo:
        repo_lower = repo.lower()
        total_before = len(incidents)
        filtered = []
        for inc in incidents:
            if not inc.get("occurrences"):
                inc["occurrences"] = _fetch_incident_occurrences(api_key, inc["id"])
            if _incident_matches_repo(inc, repo_lower):
                filtered.append(inc)
        incidents = filtered
        print(f"  Filtr repo '{repo}': {total_before} -> {len(incidents)} incydentów")

    return incidents


def _fetch_incident_occurrences(api_key: str, incident_id: int) -> list[dict]:
    """Pobiera occurrences dla incydentu (wymagane do filtrowania po repo)."""
    resp = requests.get(
        f"{BASE_URL}/incidents/secrets/{incident_id}/occurrences",
        headers=get_headers(api_key),
        params={"per_page": 20},
        timeout=REQUEST_TIMEOUT,
    )
    resp.raise_for_status()
    return resp.json()


def _incident_matches_repo(inc: dict, repo_lower: str) -> bool:
    """Sprawdza czy incydent dotyczy podanego repozytorium."""
    for occ in inc.get("occurrences") or []:
        src = occ.get("source", {})
        if src and repo_lower in str(src.get("display_name", "")).lower():
            return True
    return False


def resolve_incident(api_key: str, incident_id: int) -> tuple[bool, str]:
    """Oznacza incydent jako RESOLVED (secret_revoked=true)."""
    resp = requests.post(
        f"{BASE_URL}/incidents/secrets/{incident_id}/resolve",
        headers=get_headers(api_key),
        json={"secret_revoked": True},
        timeout=REQUEST_TIMEOUT,
    )
    if resp.status_code == 200:
        return True, "RESOLVED"
    return False, f"HTTP {resp.status_code}: {resp.text[:200]}"


def ignore_incident(api_key: str, incident_id: int, reason: str) -> tuple[bool, str]:
    """Oznacza incydent jako IGNORED z podanym powodem."""
    resp = requests.post(
        f"{BASE_URL}/incidents/secrets/{incident_id}/ignore",
        headers=get_headers(api_key),
        json={"ignore_reason": reason},
        timeout=REQUEST_TIMEOUT,
    )
    if resp.status_code == 200:
        return True, "IGNORED"
    return False, f"HTTP {resp.status_code}: {resp.text[:200]}"


def format_incident(inc: dict) -> str:
    """Formatuje incydent do wyświetlenia."""
    inc_id = inc.get("id", "?")
    status = inc.get("status", "?")
    detector = inc.get("detector", {})
    name = detector.get("display_name", inc.get("criterion", "?"))
    date = str(inc.get("date", "?"))[:10]
    severity = inc.get("severity", "?")
    tags = inc.get("tags", [])
    validity = inc.get("validity_status", "?")
    occ_count = inc.get("occurrences_count", "?")

    sources = []
    for occ in inc.get("occurrences") or []:
        src = occ.get("source", {})
        if src and src.get("display_name"):
            sources.append(src["display_name"])
    source_str = ", ".join(set(sources)) if sources else "?"

    return (
        f"  ID: {inc_id} | {name} | {date} | severity: {severity} | "
        f"validity: {validity} | occurrences: {occ_count}\n"
        f"    status: {status} | source: {source_str} | tags: {tags}"
    )


def cmd_list(
    api_key: str,
    severity: str | None = None,
    repo: str | None = None,
) -> None:
    filters = []
    if severity:
        filters.append(f"severity={severity}")
    if repo:
        filters.append(f"repo={repo}")
    filter_str = f" (filtry: {', '.join(filters)})" if filters else ""
    print(f"Pobieram otwarte incydenty{filter_str}...")

    incidents = list_open_incidents(api_key, severity=severity, repo=repo)
    if not incidents:
        print("\nBrak otwartych incydentów!")
        return

    print(f"\nOtwarte incydenty: {len(incidents)}\n")
    for i, inc in enumerate(incidents, 1):
        print(f"{i}. {format_incident(inc)}")
        print()


def cmd_resolve(
    api_key: str,
    incident_ids: list[int],
    resolve_all: bool,
    severity: str | None = None,
    repo: str | None = None,
) -> None:
    if resolve_all:
        print("Pobieram otwarte incydenty...")
        incidents = list_open_incidents(api_key, severity=severity, repo=repo)
        if not incidents:
            print("Brak otwartych incydentów.")
            return
        incident_ids = [inc["id"] for inc in incidents]
        print(f"Znaleziono {len(incident_ids)} otwartych incydentów.\n")

    ok_count = 0
    fail_count = 0
    for inc_id in incident_ids:
        success, msg = resolve_incident(api_key, inc_id)
        if success:
            print(f"  OK   ID={inc_id} -> {msg}")
            ok_count += 1
        else:
            print(f"  FAIL ID={inc_id} -> {msg}")
            fail_count += 1

    print(f"\nGotowe: {ok_count} resolved, {fail_count} failed")


def cmd_ignore(
    api_key: str,
    incident_ids: list[int],
    reason: str,
    ignore_all: bool,
    severity: str | None = None,
    repo: str | None = None,
) -> None:
    if ignore_all:
        print("Pobieram otwarte incydenty...")
        incidents = list_open_incidents(api_key, severity=severity, repo=repo)
        if not incidents:
            print("Brak otwartych incydentów.")
            return
        incident_ids = [inc["id"] for inc in incidents]
        print(f"Znaleziono {len(incident_ids)} otwartych incydentów.\n")

    ok_count = 0
    fail_count = 0
    for inc_id in incident_ids:
        success, msg = ignore_incident(api_key, inc_id, reason)
        if success:
            print(f"  OK   ID={inc_id} -> {msg} ({reason})")
            ok_count += 1
        else:
            print(f"  FAIL ID={inc_id} -> {msg}")
            fail_count += 1

    print(f"\nGotowe: {ok_count} ignored, {fail_count} failed")


_SEVERITY_CHOICES = ["critical", "high", "medium", "low", "info", "unknown"]


def _add_filter_args(parser: argparse.ArgumentParser) -> None:
    """Dodaje wspólne argumenty filtrujące do subparsera."""
    parser.add_argument(
        "--severity",
        choices=_SEVERITY_CHOICES,
        help="Filtruj po severity",
    )
    parser.add_argument(
        "--repo",
        help="Filtruj po nazwie repozytorium (dopasowanie fragmentu, case-insensitive)",
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="GitGuardian Incident Manager - zarządzanie incydentami przez API",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Przykłady:
  %(prog)s list
  %(prog)s list --severity high
  %(prog)s list --repo lenie-server
  %(prog)s list --severity critical --repo lenie
  %(prog)s resolve 12345 67890
  %(prog)s resolve --all
  %(prog)s resolve --all --severity high
  %(prog)s ignore 12345 --reason test_credential
  %(prog)s ignore --all --reason false_positive
  %(prog)s ignore --all --severity low --reason low_risk
        """,
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    list_parser = subparsers.add_parser("list", help="Wyświetl otwarte incydenty")
    _add_filter_args(list_parser)

    resolve_parser = subparsers.add_parser("resolve", help="Oznacz incydenty jako resolved")
    resolve_parser.add_argument("ids", nargs="*", type=int, help="ID incydentów do zamknięcia")
    resolve_parser.add_argument("--all", action="store_true", help="Zamknij wszystkie otwarte")
    _add_filter_args(resolve_parser)

    ignore_parser = subparsers.add_parser("ignore", help="Oznacz incydenty jako ignored")
    ignore_parser.add_argument("ids", nargs="*", type=int, help="ID incydentów do zignorowania")
    ignore_parser.add_argument("--all", action="store_true", help="Zignoruj wszystkie otwarte")
    ignore_parser.add_argument(
        "--reason",
        required=True,
        choices=["test_credential", "false_positive", "low_risk"],
        help="Powód ignorowania",
    )
    _add_filter_args(ignore_parser)

    args = parser.parse_args()
    api_key = load_api_key()

    if args.command == "list":
        cmd_list(api_key, severity=args.severity, repo=args.repo)
    elif args.command == "resolve":
        if not args.all and not args.ids:
            resolve_parser.error("Podaj ID incydentów lub użyj --all")
        cmd_resolve(api_key, args.ids or [], args.all, severity=args.severity, repo=args.repo)
    elif args.command == "ignore":
        if not args.all and not args.ids:
            ignore_parser.error("Podaj ID incydentów lub użyj --all")
        cmd_ignore(api_key, args.ids or [], args.reason, args.all, severity=args.severity, repo=args.repo)


if __name__ == "__main__":
    main()
