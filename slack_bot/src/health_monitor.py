"""Scheduled health monitoring with proactive Slack alerts.

Periodically checks backend API and database connectivity,
sends DM alerts on failures and recovery notifications.
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import TYPE_CHECKING

from src.api_client import ApiConnectionError, ApiResponseError

if TYPE_CHECKING:
    from src.api_client import LenieApiClient

logger = logging.getLogger(__name__)


class HealthStatus(Enum):
    HEALTHY = "healthy"
    DOWN = "down"


@dataclass
class ComponentState:
    name: str
    status: HealthStatus = HealthStatus.HEALTHY
    last_check: datetime | None = None
    last_alert_sent: datetime | None = None
    failure_reason: str | None = None
    down_since: datetime | None = None


class HealthMonitor:
    """Monitors backend health and sends Slack alerts on state transitions."""

    def __init__(
        self,
        api_client: LenieApiClient,
        slack_client: object,
        alert_user_id: str,
        interval: float = 300,
    ):
        if interval <= 0:
            raise ValueError(f"Health check interval must be positive, got {interval}")
        self._client = api_client
        self._slack = slack_client
        self._user_id = alert_user_id
        self._interval = interval
        self._states: dict[str, ComponentState] = {
            "backend_api": ComponentState(name="backend_api"),
            "database": ComponentState(name="database"),
        }
        self._timer: threading.Timer | None = None
        self._running = False

    # --- Individual check methods (Task 1.3, 1.4) ---

    def check_backend_api(self) -> tuple[HealthStatus, str | None]:
        """Check backend API reachability via GET /healthz."""
        try:
            self._client.check_health()
            return HealthStatus.HEALTHY, None
        except ApiConnectionError as exc:
            return HealthStatus.DOWN, exc.message
        except ApiResponseError as exc:
            return HealthStatus.DOWN, exc.message
        except Exception as exc:
            return HealthStatus.DOWN, f"Unexpected error: {exc}"

    def check_database_connectivity(self) -> tuple[HealthStatus, str | None]:
        """Check database connectivity via GET /version (requires DB)."""
        try:
            self._client.get_version()
            return HealthStatus.HEALTHY, None
        except ApiConnectionError as exc:
            return HealthStatus.DOWN, exc.message
        except ApiResponseError as exc:
            return HealthStatus.DOWN, exc.message
        except Exception as exc:
            return HealthStatus.DOWN, f"Unexpected error: {exc}"

    # --- Aggregate check (Task 1.5) ---

    def run_all_checks(self) -> list[tuple[str, HealthStatus, HealthStatus, str | None, datetime | None]]:
        """Run all health checks and return list of state transitions.

        Returns list of (component_name, old_status, new_status, reason, down_since) tuples
        for components that changed state.
        """
        now = datetime.now(tz=timezone.utc)
        checks = {
            "backend_api": self.check_backend_api,
            "database": self.check_database_connectivity,
        }
        transitions: list[tuple[str, HealthStatus, HealthStatus, str | None, datetime | None]] = []

        for component_name, check_fn in checks.items():
            state = self._states[component_name]
            new_status, reason = check_fn()
            old_status = state.status

            state.last_check = now

            if old_status != new_status:
                state.status = new_status
                state.failure_reason = reason
                down_since = state.down_since
                if new_status == HealthStatus.DOWN:
                    state.down_since = now
                    down_since = now
                elif new_status == HealthStatus.HEALTHY:
                    state.down_since = None
                transitions.append((component_name, old_status, new_status, reason, down_since))

        return transitions

    # --- Alert delivery (Task 2) ---

    def send_alert(self, component: str, reason: str, suggestion: str) -> None:
        """Send failure alert DM to configured user."""
        now = datetime.now(tz=timezone.utc)
        text = (
            f"Health Check Alert: {component}\n\n"
            f"Status: DOWN\n"
            f"Reason: {reason}\n"
            f"Time: {now.strftime('%Y-%m-%d %H:%M:%S UTC')}\n\n"
            f"Suggestion: {suggestion}"
        )
        try:
            self._slack.chat_postMessage(channel=self._user_id, text=text)
            self._states[component].last_alert_sent = now
            logger.info("Alert sent for %s: %s", component, reason)
        except Exception:
            logger.exception("Failed to send alert for %s", component)

    def send_recovery(self, component: str, downtime_seconds: float) -> None:
        """Send recovery notification DM to configured user."""
        now = datetime.now(tz=timezone.utc)
        minutes = int(downtime_seconds // 60)
        seconds = int(downtime_seconds % 60)
        duration = f"{minutes}m {seconds}s" if minutes > 0 else f"{seconds}s"
        text = (
            f"Recovery: {component} is back online\n\n"
            f"Status: HEALTHY\n"
            f"Recovery time: {now.strftime('%Y-%m-%d %H:%M:%S UTC')}\n"
            f"Approximate downtime: {duration}"
        )
        try:
            self._slack.chat_postMessage(channel=self._user_id, text=text)
            logger.info("Recovery notification sent for %s (downtime: %s)", component, duration)
        except Exception:
            logger.exception("Failed to send recovery notification for %s", component)

    def process_transitions(
        self, transitions: list[tuple[str, HealthStatus, HealthStatus, str | None, datetime | None]]
    ) -> None:
        """Process state transitions — send alerts or recovery notifications."""
        suggestions = {
            "backend_api": "Check if lenie-ai-server container is running on NAS",
            "database": "Check if lenie-ai-db container is running and PostgreSQL is accepting connections",
        }
        for component, old_status, new_status, reason, down_since in transitions:
            if old_status == HealthStatus.HEALTHY and new_status == HealthStatus.DOWN:
                self.send_alert(component, reason or "Unknown", suggestions.get(component, "Check system logs"))
            elif old_status == HealthStatus.DOWN and new_status == HealthStatus.HEALTHY:
                now = datetime.now(tz=timezone.utc)
                downtime = 0.0
                if down_since:
                    downtime = (now - down_since).total_seconds()
                self.send_recovery(component, downtime)

    # --- Scheduler (Task 3) ---

    def _run_and_reschedule(self) -> None:
        """Execute checks, process transitions, and schedule next run."""
        if not self._running:
            return
        try:
            transitions = self.run_all_checks()
            self.process_transitions(transitions)
        except Exception:
            logger.exception("Health check cycle failed")
        finally:
            if self._running:
                self._schedule_next()

    def _schedule_next(self) -> None:
        """Schedule the next health check run."""
        self._timer = threading.Timer(self._interval, self._run_and_reschedule)
        self._timer.daemon = True
        self._timer.start()

    def start(self) -> None:
        """Start the health check scheduler."""
        if self._running:
            logger.warning("Health monitor already running")
            return
        self._running = True
        logger.info("Health monitor started (interval: %ss)", self._interval)
        self._schedule_next()

    def stop(self) -> None:
        """Stop the health check scheduler."""
        self._running = False
        if self._timer is not None:
            self._timer.cancel()
            self._timer = None
        logger.info("Health monitor stopped")
