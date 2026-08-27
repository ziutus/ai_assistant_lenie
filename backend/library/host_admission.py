"""Host-health admission decisions for NAS workers.

A QNAP-side collector (``infra/docker/nas/collect-host-health.sh``) writes a
JSON snapshot of host pressure once a minute.  Before a worker claims the next
job it asks :class:`HostAdmissionGate` whether the host has spare capacity.

The gate is **disabled by default** (``HOST_ADMISSION_ENABLED=false``): until
an operator has deployed the collector and confirmed it produces valid
snapshots, ``evaluate()`` always allows the claim.  When enabled, a missing,
malformed or stale snapshot fails safe and defers the claim.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

GiB = 1024**3
MiB = 1024**2


@dataclass(frozen=True)
class AdmissionDecision:
    allowed: bool
    reason: str
    sleep_seconds: int


class HostAdmissionGate:
    """Fail safely for heavy work when the host collector is unavailable."""

    def __init__(self, config: dict) -> None:
        self.enabled = str(config.get("HOST_ADMISSION_ENABLED", "false")).strip().lower() == "true"
        self.path = Path(config.get("HOST_HEALTH_PATH", "/run/lenie-host-health/host-health.json"))
        self.max_age = int(config.get("HOST_HEALTH_MAX_AGE_SECONDS", 120))
        self.load_max = float(config.get("WORKER_LOAD_1_MAX", 2.5))
        self.mem_min = int(config.get("WORKER_MEM_AVAILABLE_MIN_BYTES", 2 * GiB))
        self.swap_max = int(config.get("WORKER_SWAP_USED_MAX_BYTES", 256 * MiB))
        self.iowait_max = float(config.get("WORKER_IOWAIT_MAX_PERCENT", 15))
        self.temp_max = float(config.get("WORKER_DISK_TEMP_MAX_C", 55))
        self.throttle_seconds = int(config.get("HOST_ADMISSION_THROTTLE_SECONDS", 60))

    def evaluate(self, now: datetime | None = None) -> AdmissionDecision:
        if not self.enabled:
            return AdmissionDecision(True, "disabled", 0)
        now = now or datetime.now(timezone.utc)
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            collected_at = datetime.fromisoformat(str(data["collected_at"]).replace("Z", "+00:00"))
        except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError):
            return AdmissionDecision(False, "host_health_unavailable", self.throttle_seconds)
        if collected_at.tzinfo is None:
            collected_at = collected_at.replace(tzinfo=timezone.utc)
        if now - collected_at.astimezone(timezone.utc) > timedelta(seconds=self.max_age):
            return AdmissionDecision(False, "host_health_stale", self.throttle_seconds)
        try:
            checks = (
                (float(data.get("load_1", 0)) > self.load_max, "load_1_high"),
                (int(float(data.get("mem_available_bytes", 0))) < self.mem_min, "memory_low"),
                (int(float(data.get("swap_used_bytes", 0))) > self.swap_max, "swap_high"),
                (float(data.get("iowait_percent", 0)) > self.iowait_max, "iowait_high"),
                (
                    max((float(value) for value in data.get("disk_temperatures_c") or []), default=0.0) > self.temp_max,
                    "disk_temperature_high",
                ),
            )
        except (TypeError, ValueError):
            return AdmissionDecision(False, "host_health_invalid", self.throttle_seconds)
        for failed, reason in checks:
            if failed:
                return AdmissionDecision(False, reason, self.throttle_seconds)
        return AdmissionDecision(True, "healthy", 0)
