#!/usr/bin/env python3
"""Manage API keys (api_keys table, Etap 8) from the command line.

Usage:
    cd backend
    python imports/api_key_admin.py create --kind user --user-id 1 --name frontend-krzysztof
    python imports/api_key_admin.py create --kind service --name chrome-extension
    python imports/api_key_admin.py list
    python imports/api_key_admin.py list --all           # include deactivated keys
    python imports/api_key_admin.py deactivate 3

The plaintext key is printed ONCE by `create` and never stored — copy it
straight into the client's configuration. Only the SHA-256 hash lands in
the database. Deactivation is soft (active=false), so `list --all` keeps
the audit trail.

NOTE: the running Flask server caches key lookups in-process (TTL 300 s /
30 s negative); changes made here are picked up after the TTL expires or
after a server restart.
"""

import argparse
import sys

from library.auth import create_api_key, deactivate_api_key
from library.db.engine import get_session
from library.db.models import ApiKey

__version__ = "0.1.0"


def _print_key_row(row: ApiKey) -> None:
    user_part = f" user_id={row.user_id}" if row.user_id is not None else ""
    state = "active" if row.active else "DEACTIVATED"
    last_used = row.last_used_at.isoformat() if row.last_used_at else "never"
    print(
        f"  [{row.id}] {row.kind:<7} {row.name:<30} prefix={row.key_prefix} "
        f"{state}{user_part} last_used={last_used}"
    )


def cmd_create(session, args) -> int:
    try:
        row, plaintext = create_api_key(session, kind=args.kind, name=args.name, user_id=args.user_id)
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(f"Created API key id={row.id} kind={row.kind} name={row.name}")
    print("Plaintext (shown ONCE, copy it now):")
    print(f"  {plaintext}")
    return 0


def cmd_list(session, args) -> int:
    query = session.query(ApiKey).order_by(ApiKey.id)
    if not args.all:
        query = query.filter(ApiKey.active.is_(True))
    rows = query.all()
    if not rows:
        print("No API keys" + ("" if args.all else " (use --all to include deactivated)"))
        return 0
    for row in rows:
        _print_key_row(row)
    return 0


def cmd_deactivate(session, args) -> int:
    try:
        row = deactivate_api_key(session, args.key_id)
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(f"Deactivated API key id={row.id} name={row.name}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Manage Lenie API keys")
    sub = parser.add_subparsers(dest="command", required=True)

    p_create = sub.add_parser("create", help="Create a key (prints plaintext once)")
    p_create.add_argument("--kind", required=True, choices=["user", "service"])
    p_create.add_argument("--name", required=True, help="Unique key name, e.g. chrome-extension")
    p_create.add_argument("--user-id", type=int, default=None, help="users.id (required for --kind user)")

    p_list = sub.add_parser("list", help="List keys (active by default)")
    p_list.add_argument("--all", action="store_true", help="Include deactivated keys")

    p_deact = sub.add_parser("deactivate", help="Soft-delete a key (active=false)")
    p_deact.add_argument("key_id", type=int)

    args = parser.parse_args()
    session = get_session()
    try:
        if args.command == "create":
            return cmd_create(session, args)
        if args.command == "list":
            return cmd_list(session, args)
        return cmd_deactivate(session, args)
    finally:
        session.close()


if __name__ == "__main__":
    sys.exit(main())
