"""Settings from environment variables only -- nothing here is ever committed (ADR-030 D2)."""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

DEFAULT_API_URL = "http://192.168.200.7:5055"


class ConfigError(RuntimeError):
    pass


@dataclass(frozen=True)
class Settings:
    api_url: str
    api_key: str
    vault: Path | None
    vault_mode: str = "local"  # "local" (disk) | "remote" (NAS gateway, ADR-030 Etap A2)


def load_settings(env: Mapping[str, str] | None = None) -> Settings:
    env = os.environ if env is None else env
    api_key = env.get("LENIE_API_KEY", "").strip()
    if not api_key:
        raise ConfigError("LENIE_API_KEY is not set (service API key, kind=service)")
    vault_raw = env.get("LENIE_OBSIDIAN_VAULT", "").strip()
    vault = None
    if vault_raw:
        vault = Path(vault_raw).resolve()
        if not vault.is_dir():
            raise ConfigError("LENIE_OBSIDIAN_VAULT does not point to an existing directory")
    mode = env.get("LENIE_VAULT_MODE", "").strip().lower() or ("local" if vault else "remote")
    if mode not in ("local", "remote"):
        raise ConfigError("LENIE_VAULT_MODE must be 'local' or 'remote'")
    if mode == "local" and vault is None:
        raise ConfigError("LENIE_VAULT_MODE=local needs LENIE_OBSIDIAN_VAULT")
    return Settings(
        api_url=env.get("LENIE_API_URL", DEFAULT_API_URL).strip().rstrip("/"),
        api_key=api_key,
        vault=vault,
        vault_mode=mode,
    )
