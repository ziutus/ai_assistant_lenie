#!/usr/bin/env python3
"""Manage secrets in HashiCorp Vault KV v2.

Supports full .env migration and individual key operations (set, delete, list, get).

Usage:
    # Full .env migration
    python scripts/env_to_vault.py upload --env dev                     # dry-run
    python scripts/env_to_vault.py upload --env dev --write             # write all
    python scripts/env_to_vault.py upload --env prod --env-file .env.prod --write

    # Single key operations
    python scripts/env_to_vault.py set --env dev KEY=value              # set/update one key
    python scripts/env_to_vault.py set --env dev K1=v1 K2=v2            # set multiple keys
    python scripts/env_to_vault.py delete --env dev KEY                 # delete one key
    python scripts/env_to_vault.py delete --env dev K1 K2               # delete multiple keys
    python scripts/env_to_vault.py list --env dev                       # list all keys
    python scripts/env_to_vault.py get --env dev KEY                    # get value of one key
"""

import argparse
import sys
from pathlib import Path

try:
    import hvac
except ImportError:
    print("ERROR: hvac package required. Install: pip install hvac")
    sys.exit(1)

# Variables that stay in the real environment -- not uploaded to Vault.
SKIP_VARS = {
    "VAULT_ADDR",
    "VAULT_TOKEN",
    "SECRETS_BACKEND",
}


def parse_env_file(path: Path) -> dict[str, str]:
    """Parse a .env file into a dict, skipping comments and empty lines."""
    result = {}
    with open(path, encoding="utf-8") as f:
        for raw_line in f:
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip()
            if len(value) >= 2 and value[0] == value[-1] and value[0] in ('"', "'"):
                value = value[1:-1]
            if not key:
                continue
            result[key] = value
    return result


def get_vault_client(env_file: str = ".env") -> tuple:
    """Read VAULT_ADDR and VAULT_TOKEN from .env, return (client, addr)."""
    env_path = Path(env_file)
    if not env_path.exists():
        print(f"ERROR: {env_path} not found")
        sys.exit(1)

    all_vars = parse_env_file(env_path)
    vault_addr = all_vars.get("VAULT_ADDR")
    vault_token = all_vars.get("VAULT_TOKEN")

    if not vault_addr:
        print("ERROR: VAULT_ADDR not found in .env")
        sys.exit(1)
    if not vault_token:
        print("ERROR: VAULT_TOKEN not found in .env")
        sys.exit(1)

    client = hvac.Client(url=vault_addr, token=vault_token)
    if not client.is_authenticated():
        print(f"ERROR: Vault authentication failed at {vault_addr}")
        sys.exit(1)

    return client, vault_addr


def read_current_secret(client, secret_path: str) -> dict[str, str]:
    """Read current secret from Vault. Returns empty dict if not found."""
    try:
        response = client.secrets.kv.v2.read_secret_version(
            path=secret_path,
            mount_point="secret",
            raise_on_deleted_version=True,
        )
        return dict(response["data"]["data"])
    except hvac.exceptions.InvalidPath:
        return {}


def mask_value(value: str) -> str:
    """Mask a secret value for display."""
    return value[:3] + "***" if len(value) > 3 else "***"


# -- Commands ---------------------------------------------------------------


def cmd_upload(args):
    """Upload all variables from .env to Vault."""
    env_path = Path(args.env_file)
    if not env_path.exists():
        print(f"ERROR: {env_path} not found")
        sys.exit(1)

    all_vars = parse_env_file(env_path)
    print(f"Parsed {len(all_vars)} variables from {env_path}")

    vault_addr = all_vars.get("VAULT_ADDR")
    vault_token = all_vars.get("VAULT_TOKEN")
    if not vault_addr or not vault_token:
        print("ERROR: VAULT_ADDR and VAULT_TOKEN must be in .env")
        sys.exit(1)

    upload_vars = {k: v for k, v in all_vars.items() if k not in SKIP_VARS}
    secret_path = f"lenie/{args.env}"

    print(f"Variables to upload: {len(upload_vars)} (skipping: {', '.join(sorted(SKIP_VARS))})")
    print(f"Vault target: {vault_addr} -> secret/{secret_path}")
    print()

    for key in sorted(upload_vars.keys()):
        print(f"  {key} = {mask_value(upload_vars[key])}")
    print()

    if not args.write:
        print("DRY RUN -- no changes made. Use --write to upload to Vault.")
        return

    client = hvac.Client(url=vault_addr, token=vault_token)
    if not client.is_authenticated():
        print(f"ERROR: Vault authentication failed at {vault_addr}")
        sys.exit(1)

    response = client.secrets.kv.v2.create_or_update_secret(
        path=secret_path,
        secret=upload_vars,
        mount_point="secret",
    )
    version = response["data"]["version"]
    print(f"SUCCESS -- wrote {len(upload_vars)} variables to secret/{secret_path} (version {version})")


def cmd_set(args):
    """Set (add or update) one or more keys using patch."""
    if not args.pairs:
        print("ERROR: provide at least one KEY=VALUE pair")
        sys.exit(1)

    updates = {}
    for pair in args.pairs:
        if "=" not in pair:
            print(f"ERROR: invalid format '{pair}', expected KEY=VALUE")
            sys.exit(1)
        key, _, value = pair.partition("=")
        updates[key.strip()] = value.strip()

    client, vault_addr = get_vault_client(args.env_file)
    secret_path = f"lenie/{args.env}"

    print(f"Vault: {vault_addr} -> secret/{secret_path}")
    print(f"Setting {len(updates)} key(s):")
    for key, value in sorted(updates.items()):
        print(f"  {key} = {mask_value(value)}")

    response = client.secrets.kv.v2.patch(
        path=secret_path,
        secret=updates,
        mount_point="secret",
    )
    version = response["data"]["version"]
    print(f"SUCCESS -- patched {len(updates)} key(s) (version {version})")


def cmd_delete(args):
    """Delete one or more keys from the secret."""
    if not args.keys:
        print("ERROR: provide at least one KEY to delete")
        sys.exit(1)

    client, vault_addr = get_vault_client(args.env_file)
    secret_path = f"lenie/{args.env}"

    current = read_current_secret(client, secret_path)
    if not current:
        print(f"ERROR: no secret found at secret/{secret_path}")
        sys.exit(1)

    missing = [k for k in args.keys if k not in current]
    if missing:
        print(f"WARNING: keys not found in Vault (skipping): {', '.join(missing)}")

    to_delete = [k for k in args.keys if k in current]
    if not to_delete:
        print("Nothing to delete.")
        return

    for key in to_delete:
        del current[key]

    print(f"Vault: {vault_addr} -> secret/{secret_path}")
    print(f"Deleting {len(to_delete)} key(s): {', '.join(to_delete)}")

    response = client.secrets.kv.v2.create_or_update_secret(
        path=secret_path,
        secret=current,
        mount_point="secret",
    )
    version = response["data"]["version"]
    print(f"SUCCESS -- removed {len(to_delete)} key(s), {len(current)} remaining (version {version})")


def cmd_list(args):
    """List all keys in the secret."""
    client, vault_addr = get_vault_client(args.env_file)
    secret_path = f"lenie/{args.env}"

    current = read_current_secret(client, secret_path)
    if not current:
        print(f"No secret found at secret/{secret_path}")
        return

    print(f"Vault: {vault_addr} -> secret/{secret_path}")
    print(f"{len(current)} key(s):")
    print()
    for key in sorted(current.keys()):
        print(f"  {key} = {mask_value(current[key])}")


def cmd_get(args):
    """Get the value of a single key."""
    if not args.key:
        print("ERROR: provide a KEY name")
        sys.exit(1)

    client, vault_addr = get_vault_client(args.env_file)
    secret_path = f"lenie/{args.env}"

    current = read_current_secret(client, secret_path)
    if args.key not in current:
        print(f"ERROR: key '{args.key}' not found at secret/{secret_path}")
        sys.exit(1)

    print(current[args.key])


# -- Main -------------------------------------------------------------------


def main():
    parser = argparse.ArgumentParser(description="Manage secrets in Vault KV v2")
    parser.add_argument(
        "--env-file",
        default=".env",
        help="Path to .env file for Vault connection (default: .env)",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # upload
    p_upload = subparsers.add_parser("upload", help="Upload all .env variables to Vault")
    p_upload.add_argument("--env", required=True, help="Environment name (dev, prod, qa)")
    p_upload.add_argument("--write", action="store_true", help="Actually write (default: dry-run)")

    # set
    p_set = subparsers.add_parser("set", help="Set (add/update) key(s) via patch")
    p_set.add_argument("--env", required=True, help="Environment name (dev, prod, qa)")
    p_set.add_argument("pairs", nargs="+", help="KEY=VALUE pairs")

    # delete
    p_delete = subparsers.add_parser("delete", help="Delete key(s) from secret")
    p_delete.add_argument("--env", required=True, help="Environment name (dev, prod, qa)")
    p_delete.add_argument("keys", nargs="+", help="Key names to delete")

    # list
    p_list = subparsers.add_parser("list", help="List all keys in secret")
    p_list.add_argument("--env", required=True, help="Environment name (dev, prod, qa)")

    # get
    p_get = subparsers.add_parser("get", help="Get value of a single key")
    p_get.add_argument("--env", required=True, help="Environment name (dev, prod, qa)")
    p_get.add_argument("key", help="Key name")

    args = parser.parse_args()

    commands = {
        "upload": cmd_upload,
        "set": cmd_set,
        "delete": cmd_delete,
        "list": cmd_list,
        "get": cmd_get,
    }
    commands[args.command](args)


if __name__ == "__main__":
    main()
