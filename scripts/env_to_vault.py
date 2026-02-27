#!/usr/bin/env python3
"""Manage secrets in HashiCorp Vault KV v2 and AWS SSM Parameter Store.

Supports full .env migration, individual key operations, and sync between backends.

Usage:
    # --- Vault commands ---
    python scripts/env_to_vault.py vault upload --env dev                  # dry-run
    python scripts/env_to_vault.py vault upload --env dev --write          # write all
    python scripts/env_to_vault.py vault set --env dev KEY=value           # patch one key
    python scripts/env_to_vault.py vault delete --env dev KEY              # delete key
    python scripts/env_to_vault.py vault list --env dev                    # list keys
    python scripts/env_to_vault.py vault get --env dev KEY                 # get value

    # --- SSM Parameter Store commands ---
    python scripts/env_to_vault.py ssm upload --env dev                    # dry-run
    python scripts/env_to_vault.py ssm upload --env dev --write            # write all
    python scripts/env_to_vault.py ssm set --env dev KEY=value             # set one key
    python scripts/env_to_vault.py ssm delete --env dev KEY                # delete key
    python scripts/env_to_vault.py ssm list --env dev                      # list keys
    python scripts/env_to_vault.py ssm get --env dev KEY                   # get value

    # --- Sync between backends ---
    python scripts/env_to_vault.py sync --env dev --from vault --to ssm    # dry-run
    python scripts/env_to_vault.py sync --env dev --from vault --to ssm --write
    python scripts/env_to_vault.py sync --env dev --from ssm --to vault --write
"""

import argparse
import sys
from pathlib import Path

# Variables that stay in the real environment -- not uploaded to backends.
SKIP_VARS = {
    "VAULT_ADDR",
    "VAULT_TOKEN",
    "SECRETS_BACKEND",
    "SECRETS_ENV",
    "PROJECT_CODE",
}

# Project code used in secret paths (Vault: {PROJECT_CODE}/{env}, SSM: /{PROJECT_CODE}/{env}/).
PROJECT_CODE = "lenie"


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


def mask_value(value: str) -> str:
    """Mask a secret value for display."""
    return value[:3] + "***" if len(value) > 3 else "***"


# ===========================================================================
# Vault helpers
# ===========================================================================


def vault_secret_path(env: str) -> str:
    """Return the Vault secret path for an environment."""
    return f"{PROJECT_CODE}/{env}"


def _require_hvac():
    try:
        import hvac
        return hvac
    except ImportError:
        print("ERROR: hvac package required. Install: pip install hvac")
        sys.exit(1)


def get_vault_client(env_file: str = ".env"):
    """Read VAULT_ADDR and VAULT_TOKEN from .env, return (client, addr)."""
    hvac = _require_hvac()
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


def vault_read_all(client, secret_path: str) -> dict[str, str]:
    """Read all keys from a Vault KV v2 secret."""
    hvac = _require_hvac()
    try:
        response = client.secrets.kv.v2.read_secret_version(
            path=secret_path,
            mount_point="secret",
            raise_on_deleted_version=True,
        )
        return dict(response["data"]["data"])
    except hvac.exceptions.InvalidPath:
        return {}


# ===========================================================================
# SSM helpers
# ===========================================================================


def _require_boto3():
    try:
        import boto3
        return boto3
    except ImportError:
        print("ERROR: boto3 package required. Install: pip install boto3")
        sys.exit(1)


def get_ssm_client(env_file: str = ".env", region: str = None, profile: str = None):
    """Create an SSM client using boto3. Returns (ssm_client, region)."""
    boto3 = _require_boto3()

    all_vars = parse_env_file(Path(env_file)) if Path(env_file).exists() else {}
    effective_region = region or all_vars.get("AWS_REGION", "eu-central-1")

    session_kwargs = {}
    if profile:
        session_kwargs["profile_name"] = profile
    session_kwargs["region_name"] = effective_region

    session = boto3.Session(**session_kwargs)
    ssm = session.client("ssm")
    return ssm, effective_region


def ssm_path_prefix(env: str) -> str:
    """Return the SSM parameter path prefix for an environment."""
    return f"/{PROJECT_CODE}/{env}/"


def ssm_read_all(ssm_client, env: str) -> dict[str, str]:
    """Read all parameters under /{PROJECT_CODE}/{env}/ from SSM."""
    prefix = ssm_path_prefix(env)
    result = {}
    paginator = ssm_client.get_paginator("get_parameters_by_path")
    for page in paginator.paginate(
        Path=prefix,
        Recursive=False,
        WithDecryption=True,
    ):
        for param in page["Parameters"]:
            # Strip prefix to get key name: /{PROJECT_CODE}/dev/MY_KEY -> MY_KEY
            key = param["Name"][len(prefix):]
            result[key] = param["Value"]
    return result


SSM_TAGS = [
    {"Key": "managed-by", "Value": "env-to-vault-script"},
    {"Key": "project", "Value": PROJECT_CODE},
]


def ssm_put_parameter(ssm_client, env: str, key: str, value: str):
    """Put a single parameter to SSM as SecureString with tags and description."""
    name = f"{ssm_path_prefix(env)}{key}"
    tags = SSM_TAGS + [{"Key": "environment", "Value": env}]
    description = f"Lenie {env} | managed by env_to_vault.py"

    # SSM doesn't allow Tags on Overwrite, so we try create first.
    try:
        ssm_client.put_parameter(
            Name=name,
            Value=value,
            Type="SecureString",
            Description=description,
            Tags=tags,
        )
    except ssm_client.exceptions.ParameterAlreadyExists:
        # Parameter exists -- overwrite (tags are preserved).
        ssm_client.put_parameter(
            Name=name,
            Value=value,
            Type="SecureString",
            Description=description,
            Overwrite=True,
        )


def ssm_delete_parameter(ssm_client, env: str, key: str):
    """Delete a single parameter from SSM."""
    name = f"{ssm_path_prefix(env)}{key}"
    ssm_client.delete_parameter(Name=name)


# ===========================================================================
# Vault commands
# ===========================================================================


def cmd_vault_upload(args):
    """Upload all variables from .env to Vault."""
    hvac = _require_hvac()
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
    secret_path = vault_secret_path(args.env)

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


def cmd_vault_set(args):
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
    secret_path = vault_secret_path(args.env)

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


def cmd_vault_delete(args):
    """Delete one or more keys from the Vault secret."""
    if not args.keys:
        print("ERROR: provide at least one KEY to delete")
        sys.exit(1)

    client, vault_addr = get_vault_client(args.env_file)
    secret_path = vault_secret_path(args.env)

    current = vault_read_all(client, secret_path)
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


def cmd_vault_list(args):
    """List all keys in the Vault secret."""
    client, vault_addr = get_vault_client(args.env_file)
    secret_path = vault_secret_path(args.env)

    current = vault_read_all(client, secret_path)
    if not current:
        print(f"No secret found at secret/{secret_path}")
        return

    print(f"Vault: {vault_addr} -> secret/{secret_path}")
    print(f"{len(current)} key(s):")
    print()
    for key in sorted(current.keys()):
        print(f"  {key} = {mask_value(current[key])}")


def cmd_vault_get(args):
    """Get the value of a single key from Vault."""
    if not args.key:
        print("ERROR: provide a KEY name")
        sys.exit(1)

    client, vault_addr = get_vault_client(args.env_file)
    secret_path = vault_secret_path(args.env)

    current = vault_read_all(client, secret_path)
    if args.key not in current:
        print(f"ERROR: key '{args.key}' not found at secret/{secret_path}")
        sys.exit(1)

    print(current[args.key])


# ===========================================================================
# SSM commands
# ===========================================================================


def cmd_ssm_upload(args):
    """Upload all variables from .env to SSM Parameter Store."""
    env_path = Path(args.env_file)
    if not env_path.exists():
        print(f"ERROR: {env_path} not found")
        sys.exit(1)

    all_vars = parse_env_file(env_path)
    print(f"Parsed {len(all_vars)} variables from {env_path}")

    upload_vars = {k: v for k, v in all_vars.items() if k not in SKIP_VARS}
    prefix = ssm_path_prefix(args.env)

    print(f"Variables to upload: {len(upload_vars)} (skipping: {', '.join(sorted(SKIP_VARS))})")
    print(f"SSM target: {prefix}*  (region: {args.region or 'from .env/default'})")
    print()

    for key in sorted(upload_vars.keys()):
        print(f"  {prefix}{key} = {mask_value(upload_vars[key])}")
    print()

    if not args.write:
        print("DRY RUN -- no changes made. Use --write to upload to SSM.")
        return

    ssm, region = get_ssm_client(args.env_file, args.region, args.profile)
    print(f"SSM region: {region}")

    for i, (key, value) in enumerate(sorted(upload_vars.items()), 1):
        ssm_put_parameter(ssm, args.env, key, value)
        if i % 10 == 0:
            print(f"  ... {i}/{len(upload_vars)}")

    print(f"SUCCESS -- wrote {len(upload_vars)} parameters to SSM under {prefix}")


def cmd_ssm_set(args):
    """Set (add/update) one or more SSM parameters."""
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

    ssm, region = get_ssm_client(args.env_file, args.region, args.profile)
    prefix = ssm_path_prefix(args.env)

    print(f"SSM: {prefix}*  (region: {region})")
    print(f"Setting {len(updates)} key(s):")
    for key, value in sorted(updates.items()):
        print(f"  {prefix}{key} = {mask_value(value)}")

    for key, value in updates.items():
        ssm_put_parameter(ssm, args.env, key, value)

    print(f"SUCCESS -- wrote {len(updates)} parameter(s)")


def cmd_ssm_delete(args):
    """Delete one or more SSM parameters."""
    if not args.keys:
        print("ERROR: provide at least one KEY to delete")
        sys.exit(1)

    ssm, region = get_ssm_client(args.env_file, args.region, args.profile)
    prefix = ssm_path_prefix(args.env)

    print(f"SSM: {prefix}*  (region: {region})")
    print(f"Deleting {len(args.keys)} key(s):")

    deleted = 0
    for key in args.keys:
        try:
            ssm_delete_parameter(ssm, args.env, key)
            print(f"  {key} -- deleted")
            deleted += 1
        except ssm.exceptions.ParameterNotFound:
            print(f"  {key} -- not found (skipping)")

    print(f"SUCCESS -- deleted {deleted} parameter(s)")


def cmd_ssm_list(args):
    """List all SSM parameters under /{PROJECT_CODE}/{env}/."""
    ssm, region = get_ssm_client(args.env_file, args.region, args.profile)
    prefix = ssm_path_prefix(args.env)

    current = ssm_read_all(ssm, args.env)
    if not current:
        print(f"No parameters found under {prefix}")
        return

    print(f"SSM: {prefix}*  (region: {region})")
    print(f"{len(current)} parameter(s):")
    print()
    for key in sorted(current.keys()):
        print(f"  {key} = {mask_value(current[key])}")


def cmd_ssm_get(args):
    """Get the value of a single SSM parameter."""
    if not args.key:
        print("ERROR: provide a KEY name")
        sys.exit(1)

    ssm, region = get_ssm_client(args.env_file, args.region, args.profile)
    name = f"{ssm_path_prefix(args.env)}{args.key}"

    try:
        response = ssm.get_parameter(Name=name, WithDecryption=True)
        print(response["Parameter"]["Value"])
    except ssm.exceptions.ParameterNotFound:
        print(f"ERROR: parameter '{name}' not found")
        sys.exit(1)


# ===========================================================================
# Sync command
# ===========================================================================


def cmd_sync(args):
    """Synchronize secrets between Vault and SSM."""
    source_name = args.source
    target_name = args.target

    if source_name == target_name:
        print("ERROR: --from and --to must be different")
        sys.exit(1)

    # Read source
    if source_name == "vault":
        client, vault_addr = get_vault_client(args.env_file)
        secret_path = vault_secret_path(args.env)
        source_data = vault_read_all(client, secret_path)
        print(f"Source: Vault ({vault_addr} -> secret/{secret_path})")
    else:
        ssm, region = get_ssm_client(args.env_file, args.region, args.profile)
        source_data = ssm_read_all(ssm, args.env)
        print(f"Source: SSM ({ssm_path_prefix(args.env)}*, region: {region})")

    if not source_data:
        print("ERROR: source has no data")
        sys.exit(1)

    print(f"  {len(source_data)} key(s) in source")

    # Read target for comparison
    if target_name == "vault":
        if source_name != "vault":
            client, vault_addr = get_vault_client(args.env_file)
        secret_path = vault_secret_path(args.env)
        target_data = vault_read_all(client, secret_path)
        print(f"Target: Vault ({vault_addr} -> secret/{secret_path})")
    else:
        if source_name != "ssm":
            ssm, region = get_ssm_client(args.env_file, args.region, args.profile)
        target_data = ssm_read_all(ssm, args.env)
        print(f"Target: SSM ({ssm_path_prefix(args.env)}*, region: {region})")

    print(f"  {len(target_data)} key(s) in target")
    print()

    # Compute diff
    new_keys = sorted(set(source_data) - set(target_data))
    changed_keys = sorted(k for k in source_data if k in target_data and source_data[k] != target_data[k])
    removed_keys = sorted(set(target_data) - set(source_data))

    if not new_keys and not changed_keys:
        print("Already in sync -- no changes needed.")
        return

    if new_keys:
        print(f"New keys ({len(new_keys)}):")
        for k in new_keys:
            print(f"  + {k} = {mask_value(source_data[k])}")
        print()

    if changed_keys:
        print(f"Changed keys ({len(changed_keys)}):")
        for k in changed_keys:
            print(f"  ~ {k} = {mask_value(target_data[k])} -> {mask_value(source_data[k])}")
        print()

    if removed_keys:
        print(f"Keys only in target ({len(removed_keys)}) -- will NOT be deleted:")
        for k in removed_keys:
            print(f"  ? {k}")
        print()

    total = len(new_keys) + len(changed_keys)
    if not args.write:
        print(f"DRY RUN -- {total} key(s) would be written. Use --write to sync.")
        return

    # Write to target
    keys_to_write = new_keys + changed_keys
    if target_name == "vault":
        # Merge into existing vault secret
        merged = dict(target_data)
        for k in keys_to_write:
            merged[k] = source_data[k]
        response = client.secrets.kv.v2.create_or_update_secret(
            path=secret_path,
            secret=merged,
            mount_point="secret",
        )
        version = response["data"]["version"]
        print(f"SUCCESS -- wrote {total} key(s) to Vault (version {version})")
    else:
        for i, key in enumerate(keys_to_write, 1):
            ssm_put_parameter(ssm, args.env, key, source_data[key])
            if i % 10 == 0:
                print(f"  ... {i}/{total}")
        print(f"SUCCESS -- wrote {total} parameter(s) to SSM")


# ===========================================================================
# CLI
# ===========================================================================


def add_ssm_args(parser):
    """Add common SSM arguments to a parser."""
    parser.add_argument("--region", default=None, help="AWS region (default: from .env or eu-central-1)")
    parser.add_argument("--profile", default=None, help="AWS profile name")


def main():
    parser = argparse.ArgumentParser(
        description="Manage secrets in Vault and AWS SSM Parameter Store"
    )
    parser.add_argument(
        "--env-file",
        default=".env",
        help="Path to .env file (default: .env)",
    )
    backend_parsers = parser.add_subparsers(dest="backend", required=True)

    # ---- vault ----
    vault_parser = backend_parsers.add_parser("vault", help="HashiCorp Vault KV v2")
    vault_sub = vault_parser.add_subparsers(dest="command", required=True)

    p = vault_sub.add_parser("upload", help="Upload all .env variables")
    p.add_argument("--env", required=True, help="Environment (dev, prod, qa)")
    p.add_argument("--write", action="store_true", help="Actually write (default: dry-run)")

    p = vault_sub.add_parser("set", help="Set key(s) via patch")
    p.add_argument("--env", required=True, help="Environment (dev, prod, qa)")
    p.add_argument("pairs", nargs="+", help="KEY=VALUE pairs")

    p = vault_sub.add_parser("delete", help="Delete key(s)")
    p.add_argument("--env", required=True, help="Environment (dev, prod, qa)")
    p.add_argument("keys", nargs="+", help="Key names")

    p = vault_sub.add_parser("list", help="List all keys")
    p.add_argument("--env", required=True, help="Environment (dev, prod, qa)")

    p = vault_sub.add_parser("get", help="Get value of a key")
    p.add_argument("--env", required=True, help="Environment (dev, prod, qa)")
    p.add_argument("key", help="Key name")

    # ---- ssm ----
    ssm_parser = backend_parsers.add_parser("ssm", help="AWS SSM Parameter Store")
    ssm_sub = ssm_parser.add_subparsers(dest="command", required=True)

    p = ssm_sub.add_parser("upload", help="Upload all .env variables")
    p.add_argument("--env", required=True, help="Environment (dev, prod, qa)")
    p.add_argument("--write", action="store_true", help="Actually write (default: dry-run)")
    add_ssm_args(p)

    p = ssm_sub.add_parser("set", help="Set key(s)")
    p.add_argument("--env", required=True, help="Environment (dev, prod, qa)")
    p.add_argument("pairs", nargs="+", help="KEY=VALUE pairs")
    add_ssm_args(p)

    p = ssm_sub.add_parser("delete", help="Delete key(s)")
    p.add_argument("--env", required=True, help="Environment (dev, prod, qa)")
    p.add_argument("keys", nargs="+", help="Key names")
    add_ssm_args(p)

    p = ssm_sub.add_parser("list", help="List all keys")
    p.add_argument("--env", required=True, help="Environment (dev, prod, qa)")
    add_ssm_args(p)

    p = ssm_sub.add_parser("get", help="Get value of a key")
    p.add_argument("--env", required=True, help="Environment (dev, prod, qa)")
    p.add_argument("key", help="Key name")
    add_ssm_args(p)

    # ---- sync ----
    sync_parser = backend_parsers.add_parser("sync", help="Sync between Vault and SSM")
    sync_parser.add_argument("--env", required=True, help="Environment (dev, prod, qa)")
    sync_parser.add_argument("--from", dest="source", required=True, choices=["vault", "ssm"], help="Source backend")
    sync_parser.add_argument("--to", dest="target", required=True, choices=["vault", "ssm"], help="Target backend")
    sync_parser.add_argument("--write", action="store_true", help="Actually sync (default: dry-run)")
    add_ssm_args(sync_parser)

    args = parser.parse_args()

    commands = {
        ("vault", "upload"): cmd_vault_upload,
        ("vault", "set"): cmd_vault_set,
        ("vault", "delete"): cmd_vault_delete,
        ("vault", "list"): cmd_vault_list,
        ("vault", "get"): cmd_vault_get,
        ("ssm", "upload"): cmd_ssm_upload,
        ("ssm", "set"): cmd_ssm_set,
        ("ssm", "delete"): cmd_ssm_delete,
        ("ssm", "list"): cmd_ssm_list,
        ("ssm", "get"): cmd_ssm_get,
    }

    if args.backend == "sync":
        cmd_sync(args)
    else:
        commands[(args.backend, args.command)](args)


if __name__ == "__main__":
    main()
