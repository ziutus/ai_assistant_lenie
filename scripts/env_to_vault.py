#!/usr/bin/env python3
"""Manage secrets in HashiCorp Vault KV v2 and AWS SSM Parameter Store.

Supports full .env migration, individual key operations, sync between backends,
YAML-driven comparison, review, removal, generation, and validation.

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

    # --- YAML-driven commands ---
    python scripts/env_to_vault.py compare --from env --to nas-vault --env dev
    python scripts/env_to_vault.py compare --from nas-vault --to aws-ssm-main --env dev --show-values
    python scripts/env_to_vault.py review --env dev
    python scripts/env_to_vault.py remove OLD_VAR --env dev                # dry-run
    python scripts/env_to_vault.py remove OLD_VAR --env dev --write
    python scripts/env_to_vault.py generate env-example --backend vault
    python scripts/env_to_vault.py generate env-example --backend env --output .env_example
    python scripts/env_to_vault.py validate env-file --backend vault
"""

import argparse
import datetime
import sys
from pathlib import Path
from typing import Any

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

# Path to the YAML classification file (used for help text and commands).
_CLASSIFICATION_YAML_PATH = Path(__file__).parent / "vars-classification.yaml"


def _get_backend_names_for_help() -> str:
    """Read backend names + descriptions from vars-classification.yaml for help text.

    Uses PyYAML (safe_load) for a lightweight read — no ruamel dependency.
    Returns a formatted string like "nas-vault (Vault on NAS), aws-ssm-main (SSM main)"
    or a generic fallback if the file is unavailable.
    """
    try:
        import yaml

        with open(_CLASSIFICATION_YAML_PATH, encoding="utf-8") as f:
            data = yaml.safe_load(f)
        backends = data.get("backends", {})
        parts = []
        for name in sorted(backends.keys()):
            desc = backends[name].get("description")
            parts.append(f"{name} - {desc}" if desc else name)
        if parts:
            return "; ".join(parts)
    except Exception:
        pass
    return "<backend names from vars-classification.yaml>"


def _load_yaml_for_help() -> dict | None:
    """Load vars-classification.yaml via PyYAML for help/error messages. Returns None on failure."""
    try:
        import yaml

        with open(_CLASSIFICATION_YAML_PATH, encoding="utf-8") as f:
            return yaml.safe_load(f)
    except Exception:
        return None


def _build_compare_help_text() -> str | None:
    """Build detailed help for the compare command showing environments and sources."""
    data = _load_yaml_for_help()
    if not data:
        return None

    backends = data.get("backends", {})
    environments = data.get("environments", {})

    lines = [
        "compare: show differences between two variable sources.",
        "",
        "Available environments (--env):",
    ]
    for env_name in sorted(environments.keys()):
        env_backends = ", ".join(environments[env_name].get("backends", []))
        lines.append(f"  {env_name:<8} backends: {env_backends}")

    lines.append("")
    lines.append("Available sources (--from / --to):")
    lines.append(f"  {'env':<16} local .env file")
    for name in sorted(backends.keys()):
        desc = backends[name].get("description", backends[name].get("type", ""))
        lines.append(f"  {name:<16} {desc}")

    lines.append("")
    lines.append("Example:")
    lines.append("  env_to_vault.py compare --env dev --from env --to nas-vault")

    return "\n".join(lines)



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
    vault_addr = all_vars.get("VAULT_ADDR") or os.environ.get("VAULT_ADDR")
    vault_token = all_vars.get("VAULT_TOKEN") or os.environ.get("VAULT_TOKEN")

    missing = []
    if not vault_addr:
        missing.append("VAULT_ADDR")
    if not vault_token:
        missing.append("VAULT_TOKEN")
    if missing:
        print(f"ERROR: Missing Vault connection variable(s) in .env or environment: {', '.join(missing)}")
        print(f"  Set them in {env_path} or export as environment variables.")
        sys.exit(1)

    client = hvac.Client(url=vault_addr, token=vault_token)
    try:
        is_auth = client.is_authenticated()
    except Exception as e:
        print(f"ERROR: Vault server not reachable at {vault_addr}")
        print(f"  Details: {e}")
        print("  Check that VAULT_ADDR points to a running Vault instance (correct host and port).")
        sys.exit(1)

    if not is_auth:
        print(f"ERROR: Vault authentication failed at {vault_addr} — check VAULT_TOKEN")
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


def ssm_read_all(ssm_client, env: str, managed_only: bool = True) -> dict[str, str]:
    """Read parameters under /{PROJECT_CODE}/{env}/ from SSM.

    Args:
        managed_only: If True (default), return only parameters created by
            this script (tagged ``managed-by=env-to-vault-script``).
            CloudFormation-managed parameters are excluded.
    """
    prefix = ssm_path_prefix(env)
    result = {}

    if managed_only:
        # Use describe_parameters to find only our tagged parameters,
        # then fetch their values with GetParameters (supports decryption).
        tag_filters = [
            {"Key": "tag:managed-by", "Values": ["env-to-vault-script"]},
            {"Key": "Name", "Option": "BeginsWith", "Values": [prefix]},
        ]
        names = []
        paginator = ssm_client.get_paginator("describe_parameters")
        for page in paginator.paginate(ParameterFilters=tag_filters):
            for param in page["Parameters"]:
                names.append(param["Name"])

        # GetParameters accepts max 10 names per call
        for i in range(0, len(names), 10):
            batch = names[i:i + 10]
            response = ssm_client.get_parameters(Names=batch, WithDecryption=True)
            for param in response["Parameters"]:
                key = param["Name"][len(prefix):]
                result[key] = param["Value"]
    else:
        paginator = ssm_client.get_paginator("get_parameters_by_path")
        for page in paginator.paginate(
            Path=prefix,
            Recursive=False,
            WithDecryption=True,
        ):
            for param in page["Parameters"]:
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
# YAML classification helpers
# ===========================================================================

SUPPORTED_BACKEND_TYPES = ("vault_kv2", "aws_ssm")

_classification_cache = None
_client_cache: dict[str, Any] = {}


def _require_ruamel():
    try:
        from ruamel.yaml import YAML
        return YAML(typ="rt")
    except ImportError:
        print("ERROR: ruamel.yaml package required. Install: pip install ruamel.yaml")
        sys.exit(1)


def load_classification(yaml_path: str | Path | None = None) -> dict:
    """Load and cache vars-classification.yaml. Returns parsed data."""
    global _classification_cache
    if _classification_cache is not None:
        return _classification_cache

    if yaml_path is None:
        yaml_path = Path(__file__).parent / "vars-classification.yaml"
    yaml_path = Path(yaml_path)

    if not yaml_path.exists():
        print(f"ERROR: {yaml_path} not found")
        sys.exit(1)

    yaml = _require_ruamel()
    try:
        with open(yaml_path, encoding="utf-8") as f:
            data = yaml.load(f)
    except Exception as e:
        print(f"ERROR: Failed to parse {yaml_path}: {e}")
        sys.exit(1)

    _classification_cache = data
    return data


def save_classification(classification, yaml_path: str | Path | None = None):
    """Write classification back to YAML with round-trip preservation."""
    global _classification_cache
    if yaml_path is None:
        yaml_path = Path(__file__).parent / "vars-classification.yaml"
    yaml_path = Path(yaml_path)

    yaml = _require_ruamel()
    with open(yaml_path, "w", encoding="utf-8") as f:
        yaml.dump(classification, f)

    _classification_cache = None


def get_backends_for_env(classification, env: str) -> list[tuple[str, dict]]:
    """Return list of (backend_name, backend_def) for an environment."""
    environments = classification.get("environments", {})
    if env not in environments:
        available = ", ".join(sorted(environments.keys()))
        print(f"ERROR: Environment '{env}' not defined in vars-classification.yaml. Available: {available}")
        sys.exit(1)

    backend_names = environments[env].get("backends", [])
    backends_section = classification.get("backends", {})
    result = []
    for name in backend_names:
        if name not in backends_section:
            print(f"ERROR: Backend '{name}' referenced in environment '{env}' but not defined in backends section")
            sys.exit(1)
        result.append((name, dict(backends_section[name])))
    return result


def get_all_variables(classification) -> dict[str, dict]:
    """Flatten all groups into {var_name: {group, type, ...}}."""
    result = {}
    for group_name, group_data in classification.get("groups", {}).items():
        for var_name, var_def in group_data.get("variables", {}).items():
            entry = dict(var_def)
            entry["group"] = group_name
            result[var_name] = entry
    return result


def get_bootstrap_variables(classification) -> dict[str, dict]:
    """Return dict of variables in bootstrap group only."""
    bootstrap = classification.get("groups", {}).get("bootstrap", {})
    result = {}
    for var_name, var_def in bootstrap.get("variables", {}).items():
        entry = dict(var_def)
        entry["group"] = "bootstrap"
        result[var_name] = entry
    return result


def get_derived_ssm_type(var_def: dict) -> str:
    """Return SSM parameter type: explicit ssm_type, or derived from type field."""
    if "ssm_type" in var_def:
        return var_def["ssm_type"]
    return "SecureString" if var_def.get("type") == "secret" else "String"


def resolve_backend_client(backend_def: dict, backend_name: str, args) -> Any:
    """Return appropriate client for backend, caching by name."""
    if backend_name in _client_cache:
        return _client_cache[backend_name]

    backend_type = backend_def.get("type", "")
    if backend_type == "vault_kv2":
        client, _ = get_vault_client(args.env_file)
        _client_cache[backend_name] = client
        return client
    elif backend_type == "aws_ssm":
        profile = backend_def.get("profile")
        region = backend_def.get("region")
        client, _ = get_ssm_client(args.env_file, region=region, profile=profile)
        _client_cache[backend_name] = client
        return client
    else:
        print(
            f"ERROR: Backend type '{backend_type}' is not supported. "
            f"Supported types: {', '.join(SUPPORTED_BACKEND_TYPES)}"
        )
        sys.exit(1)


def read_backend_data(backend_def: dict, client, env: str) -> dict[str, str]:
    """Read all key-value pairs from a backend."""
    backend_type = backend_def.get("type", "")
    if backend_type == "vault_kv2":
        return vault_read_all(client, vault_secret_path(env))
    elif backend_type == "aws_ssm":
        return ssm_read_all(client, env)
    return {}


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
# Compare command
# ===========================================================================


def _resolve_source_data(source_name: str, classification, args) -> tuple[str, dict[str, str]]:
    """Resolve a source name (backend name or 'env') to (label, data)."""
    if source_name == "env":
        env_path = Path(args.env_file)
        if not env_path.exists():
            print(f"ERROR: .env file not found: {env_path.resolve()}")
            print(f"  Hint: use --env-file to specify the path (before the command):")
            print(f"  {Path(sys.argv[0]).name} --env-file PATH compare --from env --to ... --env dev")
            sys.exit(1)
        return f"env ({env_path})", parse_env_file(env_path)

    backends_section = classification.get("backends", {})
    if source_name not in backends_section:
        available = ", ".join(sorted(backends_section.keys()))
        print(f"ERROR: Unknown source '{source_name}'. Available backends: {available}, env")
        sys.exit(1)

    backend_def = dict(backends_section[source_name])
    try:
        client = resolve_backend_client(backend_def, source_name, args)
        data = read_backend_data(backend_def, client, args.env)
    except SystemExit:
        raise
    except Exception as e:
        print(f"ERROR: Failed to connect to '{source_name}': {e}")
        sys.exit(1)

    return source_name, data


def cmd_compare(args):
    """Compare variables between two sources."""
    missing = [name for name, val in [("--env", args.env), ("--from", args.source), ("--to", args.target)] if not val]
    if missing:
        help_text = _build_compare_help_text()
        if help_text:
            print(help_text)
        print(f"\nError: missing required arguments: {', '.join(missing)}")
        sys.exit(2)

    # Catch common mistake: --env expects environment name, not a file path
    if "/" in args.env or "\\" in args.env or args.env.endswith(".env"):
        print(f"ERROR: --env expects an environment name (dev, prod, qa), not a file path.")
        print(f"  Got: --env {args.env}")
        print(f"  Hint: use --env-file for the .env file path (before the command):")
        print(f"  {Path(sys.argv[0]).name} --env-file {args.env} compare --from ... --to ... --env dev")
        sys.exit(2)

    classification = load_classification()

    source_label, source_data = _resolve_source_data(args.source, classification, args)
    target_label, target_data = _resolve_source_data(args.target, classification, args)

    print(f"Comparing: {source_label} -> {target_label} (env: {args.env})")
    print()

    # Filter out SKIP_VARS — these stay in local environment only, never uploaded to backends
    source_keys = set(source_data) - SKIP_VARS
    target_keys = set(target_data) - SKIP_VARS

    only_source = sorted(source_keys - target_keys)
    only_target = sorted(target_keys - source_keys)
    common = source_keys & target_keys
    different = sorted(k for k in common if source_data[k] != target_data[k])
    in_sync = sorted(k for k in common if source_data[k] == target_data[k])

    if not only_source and not only_target and not different:
        print(f"Sources are identical ({len(in_sync)} keys in sync).")
        return

    show = args.show_values
    if show:
        print("WARNING: Showing unmasked values!")
        print()

    val = (lambda v: v) if show else mask_value

    if only_source:
        print(f"Only in {source_label} ({len(only_source)}):")
        for k in only_source:
            print(f"  + {k} = {val(source_data[k])}")
        print()

    if only_target:
        print(f"Only in {target_label} ({len(only_target)}):")
        for k in only_target:
            print(f"  + {k} = {val(target_data[k])}")
        print()

    if different:
        print(f"Different values ({len(different)}):")
        for k in different:
            print(f"  ~ {k} = {val(source_data[k])} -> {val(target_data[k])}")
        print()

    print(f"In sync: {len(in_sync)} keys")


# ===========================================================================
# Generate command
# ===========================================================================


def cmd_generate(args):
    """Generate .env_example from vars-classification.yaml."""
    classification = load_classification()
    backend_type = args.backend_type
    all_vars = get_all_variables(classification)
    bootstrap_vars = get_bootstrap_variables(classification)

    vault_only_vars = {"VAULT_ADDR", "VAULT_TOKEN", "VAULT_ENV"}

    if backend_type == "vault":
        selected = bootstrap_vars
    elif backend_type == "aws":
        selected = {k: v for k, v in bootstrap_vars.items() if k not in vault_only_vars}
    else:
        selected = all_vars

    today = datetime.date.today().isoformat()
    lines = [
        "# Generated by env_to_vault.py from vars-classification.yaml",
        f"# Backend: {backend_type}",
        f"# Date: {today}",
        "",
    ]

    current_group = None
    for var_name in sorted(selected.keys(), key=lambda k: (selected[k]["group"], k)):
        var_def = selected[var_name]
        group = var_def["group"]
        if group != current_group:
            if current_group is not None:
                lines.append("")
            lines.append(f"# --- {group} ---")
            current_group = group

        desc = var_def.get("description", "")
        if desc:
            lines.append(f"# {desc}")

        value = var_def.get("example", var_def.get("default", ""))
        lines.append(f"{var_name}=\"{value}\"")

    output = "\n".join(lines) + "\n"

    if args.output:
        Path(args.output).write_text(output, encoding="utf-8")
        print(f"Written to {args.output}")
    else:
        print(output, end="")


# ===========================================================================
# Validate command
# ===========================================================================


def cmd_validate(args):
    """Validate .env file against vars-classification.yaml."""
    classification = load_classification()
    env_path = Path(args.env_file)
    if not env_path.exists():
        print(f"ERROR: {env_path} not found")
        sys.exit(1)

    env_data = parse_env_file(env_path)
    all_vars = get_all_variables(classification)
    bootstrap_vars = get_bootstrap_variables(classification)
    backend_type = args.backend_type

    vault_only_vars = {"VAULT_ADDR", "VAULT_TOKEN", "VAULT_ENV"}

    if backend_type == "vault":
        expected_bootstrap = set(bootstrap_vars.keys())
    elif backend_type == "aws":
        expected_bootstrap = set(bootstrap_vars.keys()) - vault_only_vars
    else:
        expected_bootstrap = set(bootstrap_vars.keys())

    print(f"Validating {env_path} for backend: {backend_type}")
    print()

    issues = False

    # Check bootstrap presence
    present_bootstrap = set(env_data.keys()) & expected_bootstrap
    missing_bootstrap = sorted(expected_bootstrap - set(env_data.keys()))
    print(f"Bootstrap variables present: {len(present_bootstrap)}/{len(expected_bootstrap)}")
    if missing_bootstrap:
        print(f"  Missing: {', '.join(missing_bootstrap)}")
        issues = True
    print()

    # Check non-bootstrap excess (for vault/aws modes)
    if backend_type in ("vault", "aws"):
        non_bootstrap = sorted(k for k in env_data if k in all_vars and k not in bootstrap_vars)
        if non_bootstrap:
            backend_label = "Vault" if backend_type == "vault" else "SSM"
            print(f"Non-bootstrap variables found (should be in {backend_label}): {len(non_bootstrap)}")
            for k in non_bootstrap:
                vdef = all_vars[k]
                print(f"  - {k} (group: {vdef['group']}, type: {vdef.get('type', '?')})")
            print()
            issues = True

    # Check unknown variables
    unknown = sorted(k for k in env_data if k not in all_vars)
    if unknown:
        print(f"Unknown variables (not in vars-classification.yaml): {len(unknown)}")
        for k in unknown:
            print(f"  - {k}")
        print()
        issues = True

    if not issues:
        print("OK -- .env file is clean for the selected backend.")

    sys.exit(1 if issues else 0)


# ===========================================================================
# Remove command
# ===========================================================================


def cmd_remove(args):
    """Remove variable(s) from all backends in an environment + YAML."""
    classification = load_classification()
    backends = get_backends_for_env(classification, args.env)
    all_vars = get_all_variables(classification)

    for key in args.keys:
        print(f"Remove {key} from environment '{args.env}':")
        print()

        # Check each backend
        for backend_name, backend_def in backends:
            backend_type = backend_def.get("type", "")
            try:
                client = resolve_backend_client(backend_def, backend_name, args)
                data = read_backend_data(backend_def, client, args.env)
                exists = key in data
            except SystemExit:
                raise
            except Exception as e:
                print(f"  {backend_name}: ERROR connecting -- {e}")
                continue

            if backend_type == "vault_kv2":
                path = f"secret/{vault_secret_path(args.env)}"
            else:
                path = f"{ssm_path_prefix(args.env)}{key}"

            if exists:
                print(f"  {backend_name} ({path}): exists -> will remove")
            else:
                print(f"  {backend_name} ({path}): not found (skipping)")

        # Check YAML
        if key in all_vars:
            group = all_vars[key]["group"]
            print(f"  vars-classification.yaml (group: {group}): exists -> will remove")
        else:
            print("  vars-classification.yaml: not found")

        print()

    if not args.write:
        print("DRY RUN -- no changes made. Use --write to execute.")
        return

    # Execute removal
    for key in args.keys:
        for backend_name, backend_def in backends:
            backend_type = backend_def.get("type", "")
            try:
                client = resolve_backend_client(backend_def, backend_name, args)
            except SystemExit:
                raise
            except Exception:
                continue

            if backend_type == "vault_kv2":
                current = vault_read_all(client, vault_secret_path(args.env))
                if key in current:
                    del current[key]
                    client.secrets.kv.v2.create_or_update_secret(
                        path=vault_secret_path(args.env),
                        secret=current,
                        mount_point="secret",
                    )
                    print(f"  {backend_name}: {key} removed from Vault")
                else:
                    print(f"  {backend_name}: {key} not found (skipping)")
            elif backend_type == "aws_ssm":
                try:
                    ssm_delete_parameter(client, args.env, key)
                    print(f"  {backend_name}: {key} removed from SSM")
                except Exception:
                    print(f"  {backend_name}: {key} not found (skipping)")

        # Remove from YAML
        for group_name, group_data in classification.get("groups", {}).items():
            variables = group_data.get("variables", {})
            if key in variables:
                del variables[key]
                print(f"  YAML: {key} removed from group '{group_name}'")
                break

    save_classification(classification)
    print()
    print("SUCCESS -- removal complete.")


# ===========================================================================
# Review command
# ===========================================================================


def build_review_data(classification, env: str, args, backend_filter: str | None = None) -> dict:
    """Build unified review data for all YAML-defined variables vs backends."""
    backends = get_backends_for_env(classification, env)
    if backend_filter:
        matched = [(n, d) for n, d in backends if n == backend_filter]
        if not matched:
            available = ", ".join(n for n, _ in backends)
            print(f"ERROR: Backend '{backend_filter}' not found for environment '{env}'. Available: {available}")
            sys.exit(1)
        backends = matched
    all_vars = get_all_variables(classification)

    backend_data = {}
    unavailable = []
    for backend_name, backend_def in backends:
        try:
            client = resolve_backend_client(backend_def, backend_name, args)
            backend_data[backend_name] = read_backend_data(backend_def, client, env)
        except SystemExit:
            raise
        except Exception as e:
            print(f"WARNING: {backend_name} unavailable -- {e}")
            backend_data[backend_name] = None
            unavailable.append(backend_name)

    # Build per-variable presence map
    var_status = {}
    for var_name, var_def in all_vars.items():
        presence = {}
        for backend_name, _ in backends:
            data = backend_data[backend_name]
            if data is None:
                presence[backend_name] = None  # unavailable
            else:
                presence[backend_name] = var_name in data
        var_status[var_name] = {
            "group": var_def["group"],
            "type": var_def.get("type", "?"),
            "presence": presence,
        }

    # Detect orphans (in backends but not in YAML)
    all_yaml_keys = set(all_vars.keys())
    orphans = {}
    for backend_name, _ in backends:
        data = backend_data[backend_name]
        if data is None:
            continue
        for key in data:
            if key not in all_yaml_keys:
                if key not in orphans:
                    orphans[key] = {}
                orphans[key][backend_name] = True

    # Fill missing backends for orphans
    for orphan_key, orphan_presence in orphans.items():
        for backend_name, _ in backends:
            if backend_name not in orphan_presence:
                data = backend_data[backend_name]
                if data is None:
                    orphan_presence[backend_name] = None
                else:
                    orphan_presence[backend_name] = orphan_key in data

    return {
        "backends": backends,
        "var_status": var_status,
        "orphans": orphans,
        "unavailable": unavailable,
    }


def display_review(review_data: dict):
    """Display review table grouped by variable group."""
    backends = review_data["backends"]
    var_status = review_data["var_status"]
    orphans = review_data["orphans"]
    unavailable = review_data["unavailable"]

    backend_names = [name for name, _ in backends]
    print(f"Backends: {', '.join(backend_names)}")
    if unavailable:
        print(f"  Unavailable: {', '.join(unavailable)}")
    print()

    # Group variables
    groups: dict[str, list[str]] = {}
    for var_name, status in var_status.items():
        group = status["group"]
        groups.setdefault(group, []).append(var_name)

    synced = 0
    gaps = 0

    for group_name in sorted(groups.keys()):
        var_names = sorted(groups[group_name])
        print(f"GROUP: {group_name} ({len(var_names)} vars)")
        for var_name in var_names:
            status = var_status[var_name]
            presence = status["presence"]
            var_type = status["type"]

            all_present = all(v is True for v in presence.values() if v is not None)
            has_gap = any(v is False for v in presence.values())

            if all_present and not has_gap:
                icon = "ok"
                synced += 1
            else:
                icon = "GAP"
                gaps += 1

            parts = []
            for bname in backend_names:
                val = presence.get(bname)
                if val is None:
                    parts.append(f"{bname}: ?")
                elif val:
                    parts.append(f"{bname}: +")
                else:
                    parts.append(f"{bname}: -")

            print(f"  [{icon:>4}] {var_name:<30} {' '.join(parts)}  {var_type}")
        print()

    # Orphans
    if orphans:
        print(f"ORPHANS (in backends but NOT in YAML): {len(orphans)}")
        for orphan_key in sorted(orphans.keys()):
            orphan_presence = orphans[orphan_key]
            parts = []
            for bname in backend_names:
                val = orphan_presence.get(bname)
                if val is None:
                    parts.append(f"{bname}: ?")
                elif val:
                    parts.append(f"{bname}: +")
                else:
                    parts.append(f"{bname}: -")
            print(f"  [orphan] {orphan_key:<30} {' '.join(parts)}")
        print()

    defined = len(var_status)
    orphan_count = len(orphans)
    print(f"Summary: {defined} defined, {synced} synced, {gaps} gaps, {orphan_count} orphans")


def cmd_review(args):
    """Interactive review of YAML-defined variables vs actual backend state."""
    classification = load_classification()
    env = args.env
    backend_filter = getattr(args, "only_backend", None)
    # Validate environment
    get_backends_for_env(classification, env)

    header = f"Environment '{env}' review"
    if backend_filter:
        header += f" (backend: {backend_filter})"
    print(header)
    print("Note: YAML changes made outside this session will be overwritten by save operations.")
    print()

    review_data = build_review_data(classification, env, args, backend_filter=backend_filter)
    display_review(review_data)
    print()

    while True:
        print("Actions: [d] Delete variable  [a] Add orphan to YAML  [q] Quit")
        try:
            action = input("> ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            print()
            break

        if action == "q":
            break
        elif action == "d":
            var_name = input("Variable name to delete: ").strip()
            if not var_name:
                continue
            confirm = input(f"Delete '{var_name}' from all backends + YAML? [y/N]: ").strip().lower()
            if confirm not in ("y", "yes"):
                print("Cancelled.")
                continue

            # Reuse remove logic
            class FakeArgs:
                pass
            fake = FakeArgs()
            fake.keys = [var_name]
            fake.env = env
            fake.write = True
            fake.env_file = args.env_file
            if hasattr(args, "region"):
                fake.region = args.region
            if hasattr(args, "profile"):
                fake.profile = args.profile
            cmd_remove(fake)

            # Reload and refresh
            global _classification_cache
            _classification_cache = None
            _client_cache.clear()
            classification = load_classification()
            print()
            review_data = build_review_data(classification, env, args, backend_filter=backend_filter)
            display_review(review_data)
            print()

        elif action == "a":
            orphan_name = input("Orphan variable name to add: ").strip()
            if not orphan_name:
                continue
            if orphan_name not in review_data["orphans"]:
                print(f"'{orphan_name}' is not an orphan.")
                continue

            groups_list = sorted(classification.get("groups", {}).keys())
            print(f"Available groups: {', '.join(groups_list)}")
            group = input("Group: ").strip()
            if group not in classification.get("groups", {}):
                print(f"Unknown group '{group}'.")
                continue

            var_type = input("Type (secret/config): ").strip()
            if var_type not in ("secret", "config"):
                print("Type must be 'secret' or 'config'.")
                continue

            description = input("Description: ").strip()

            variables = classification["groups"][group].get("variables", {})
            variables[orphan_name] = {
                "description": description,
                "type": var_type,
                "required": False,
            }
            save_classification(classification)
            print(f"Added '{orphan_name}' to group '{group}'.")

            # Reload and refresh
            _classification_cache = None
            _client_cache.clear()
            classification = load_classification()
            print()
            review_data = build_review_data(classification, env, args, backend_filter=backend_filter)
            display_review(review_data)
            print()


# ===========================================================================
# CLI
# ===========================================================================


def add_ssm_args(parser):
    """Add common SSM arguments to a parser."""
    parser.add_argument("--region", default=None, help="AWS region (default: from .env or eu-central-1)")
    parser.add_argument("--profile", default=None, help="AWS profile name")


def main():
    epilog = """\
examples:
  # Vault - upload .env to dev environment (dry-run first, then write)
  %(prog)s vault upload --env dev
  %(prog)s vault upload --env dev --write

  # Vault - read / write individual keys
  %(prog)s vault list --env dev
  %(prog)s vault get --env dev MY_KEY
  %(prog)s vault set --env dev MY_KEY=value

  # SSM Parameter Store - same interface
  %(prog)s ssm upload --env dev --write
  %(prog)s ssm list --env dev

  # Sync between backends
  %(prog)s sync --env dev --from vault --to ssm
  %(prog)s sync --env dev --from vault --to ssm --write

  # YAML-driven operations
  %(prog)s compare --from env --to nas-vault --env dev
  %(prog)s review --env dev
  %(prog)s remove OLD_VAR --env dev --write
  %(prog)s generate env-example --backend vault
  %(prog)s validate env-file --backend vault
"""
    parser = argparse.ArgumentParser(
        description="Manage secrets in HashiCorp Vault KV v2 and AWS SSM Parameter Store.\n"
                    "Choose a command below to get started.",
        epilog=epilog,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--env-file",
        default=".env",
        help="Path to .env file (default: .env)",
    )
    backend_parsers = parser.add_subparsers(
        dest="backend",
        required=True,
        title="commands",
        metavar="COMMAND",
    )

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

    # ---- compare ----
    _backends = _get_backend_names_for_help()
    compare_parser = backend_parsers.add_parser(
        "compare",
        help="Compare variables between two sources",
        description="Compare variables between two sources.\n"
                    "Run 'compare' without arguments to see available environments and backends.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    compare_parser.add_argument("--env", default=None, help="Environment (required: dev, prod, qa)")
    compare_parser.add_argument(
        "--from", dest="source", default=None,
        help=f"Source (required): 'env' (local .env file) or backend name ({_backends})",
    )
    compare_parser.add_argument(
        "--to", dest="target", default=None,
        help=f"Target (required): 'env' (local .env file) or backend name ({_backends})",
    )
    compare_parser.add_argument("--show-values", action="store_true", help="Show unmasked values")
    add_ssm_args(compare_parser)

    # ---- review ----
    review_parser = backend_parsers.add_parser("review", help="Interactive review of YAML vs backend state")
    review_parser.add_argument("--env", required=True, help="Environment (dev, prod, qa)")
    review_parser.add_argument("--only-backend", default=None, dest="only_backend",
                               help="Review only this backend (e.g. nas-vault, aws-ssm-main)")
    add_ssm_args(review_parser)

    # ---- remove ----
    remove_parser = backend_parsers.add_parser(
        "remove",
        help="Remove variable(s) from ALL backends in an environment + YAML",
    )
    remove_parser.add_argument("keys", nargs="+", help="Variable names to remove")
    remove_parser.add_argument("--env", required=True, help="Environment (dev, prod, qa)")
    remove_parser.add_argument("--write", action="store_true", help="Actually remove (default: dry-run)")
    add_ssm_args(remove_parser)

    # ---- generate ----
    generate_parser = backend_parsers.add_parser("generate", help="Generate files from YAML classification")
    generate_sub = generate_parser.add_subparsers(dest="generate_command", required=True)
    p = generate_sub.add_parser("env-example", help="Generate .env_example from YAML")
    p.add_argument("--backend", dest="backend_type", required=True, choices=["vault", "aws", "env"],
                    help="Target backend type")
    p.add_argument("--output", default=None, help="Output file path (default: stdout)")

    # ---- validate ----
    validate_parser = backend_parsers.add_parser("validate", help="Validate files against YAML classification")
    validate_sub = validate_parser.add_subparsers(dest="validate_command", required=True)
    p = validate_sub.add_parser("env-file", help="Validate .env file")
    p.add_argument("--backend", dest="backend_type", required=True, choices=["vault", "aws", "env"],
                    help="Expected backend type")

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
    elif args.backend == "compare":
        cmd_compare(args)
    elif args.backend == "review":
        cmd_review(args)
    elif args.backend == "remove":
        cmd_remove(args)
    elif args.backend == "generate":
        cmd_generate(args)
    elif args.backend == "validate":
        cmd_validate(args)
    else:
        commands[(args.backend, args.command)](args)


if __name__ == "__main__":
    main()
