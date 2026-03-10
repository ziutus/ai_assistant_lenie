"""Unit tests for health_monitor module."""

from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest

from src.api_client import ApiConnectionError, ApiResponseError
from src.health_monitor import (
    ComponentState,
    HealthMonitor,
    HealthStatus,
)


# --- HealthStatus enum tests ---


class TestHealthStatus:
    def test_healthy_value(self):
        assert HealthStatus.HEALTHY.value == "healthy"

    def test_down_value(self):
        assert HealthStatus.DOWN.value == "down"


# --- ComponentState dataclass tests ---


class TestComponentState:
    def test_default_state_is_healthy(self):
        state = ComponentState(name="backend_api")
        assert state.status == HealthStatus.HEALTHY
        assert state.last_check is None
        assert state.last_alert_sent is None
        assert state.failure_reason is None

    def test_state_with_values(self):
        now = datetime.now(tz=timezone.utc)
        state = ComponentState(
            name="database",
            status=HealthStatus.DOWN,
            last_check=now,
            last_alert_sent=now,
            failure_reason="Connection refused",
        )
        assert state.name == "database"
        assert state.status == HealthStatus.DOWN
        assert state.failure_reason == "Connection refused"


# --- HealthMonitor state tracking tests (Task 1.2) ---


class TestHealthMonitorStateTracking:
    def setup_method(self):
        self.mock_client = MagicMock()
        self.mock_slack_client = MagicMock()
        self.monitor = HealthMonitor(
            api_client=self.mock_client,
            slack_client=self.mock_slack_client,
            alert_user_id="U12345",
            interval=60,
        )

    def test_initial_state_all_healthy(self):
        for state in self.monitor._states.values():
            assert state.status == HealthStatus.HEALTHY

    def test_components_tracked(self):
        assert "backend_api" in self.monitor._states
        assert "database" in self.monitor._states


# --- check_backend_api tests (Task 1.3) ---


class TestCheckBackendApi:
    def setup_method(self):
        self.mock_client = MagicMock()
        self.mock_slack_client = MagicMock()
        self.monitor = HealthMonitor(
            api_client=self.mock_client,
            slack_client=self.mock_slack_client,
            alert_user_id="U12345",
            interval=60,
        )

    def test_healthy_check(self):
        self.mock_client.check_health.return_value = {"status": "ok"}
        status, reason = self.monitor.check_backend_api()
        assert status == HealthStatus.HEALTHY
        assert reason is None

    def test_connection_error_returns_down(self):
        self.mock_client.check_health.side_effect = ApiConnectionError("timeout")
        status, reason = self.monitor.check_backend_api()
        assert status == HealthStatus.DOWN
        assert "timeout" in reason

    def test_response_error_returns_down(self):
        self.mock_client.check_health.side_effect = ApiResponseError("500", 500)
        status, reason = self.monitor.check_backend_api()
        assert status == HealthStatus.DOWN
        assert "500" in reason

    def test_unexpected_exception_returns_down(self):
        self.mock_client.check_health.side_effect = RuntimeError("unexpected")
        status, reason = self.monitor.check_backend_api()
        assert status == HealthStatus.DOWN
        assert "unexpected" in reason.lower() or "Unexpected" in reason


# --- check_database_connectivity tests (Task 1.4) ---


class TestCheckDatabaseConnectivity:
    def setup_method(self):
        self.mock_client = MagicMock()
        self.mock_slack_client = MagicMock()
        self.monitor = HealthMonitor(
            api_client=self.mock_client,
            slack_client=self.mock_slack_client,
            alert_user_id="U12345",
            interval=60,
        )

    def test_healthy_db_check(self):
        self.mock_client.get_version.return_value = {"app_version": "1.0"}
        status, reason = self.monitor.check_database_connectivity()
        assert status == HealthStatus.HEALTHY
        assert reason is None

    def test_connection_error_returns_down(self):
        self.mock_client.get_version.side_effect = ApiConnectionError("no connection")
        status, reason = self.monitor.check_database_connectivity()
        assert status == HealthStatus.DOWN
        assert reason is not None

    def test_response_error_returns_down(self):
        self.mock_client.get_version.side_effect = ApiResponseError("DB error", 500)
        status, reason = self.monitor.check_database_connectivity()
        assert status == HealthStatus.DOWN

    def test_unexpected_exception_returns_down(self):
        self.mock_client.get_version.side_effect = Exception("boom")
        status, reason = self.monitor.check_database_connectivity()
        assert status == HealthStatus.DOWN


# --- run_all_checks tests (Task 1.5) ---


class TestRunAllChecks:
    def setup_method(self):
        self.mock_client = MagicMock()
        self.mock_slack_client = MagicMock()
        self.monitor = HealthMonitor(
            api_client=self.mock_client,
            slack_client=self.mock_slack_client,
            alert_user_id="U12345",
            interval=60,
        )

    def test_all_healthy_no_transitions(self):
        self.mock_client.check_health.return_value = {"status": "ok"}
        self.mock_client.get_version.return_value = {"app_version": "1.0"}
        transitions = self.monitor.run_all_checks()
        assert transitions == []

    def test_backend_goes_down_returns_transition(self):
        self.mock_client.check_health.side_effect = ApiConnectionError("timeout")
        self.mock_client.get_version.return_value = {"app_version": "1.0"}
        transitions = self.monitor.run_all_checks()
        assert len(transitions) == 1
        assert transitions[0][0] == "backend_api"
        assert transitions[0][1] == HealthStatus.HEALTHY  # old
        assert transitions[0][2] == HealthStatus.DOWN  # new
        assert transitions[0][4] is not None  # down_since is set

    def test_recovery_returns_transition(self):
        # First: go down
        self.mock_client.check_health.side_effect = ApiConnectionError("timeout")
        self.mock_client.get_version.return_value = {"app_version": "1.0"}
        self.monitor.run_all_checks()

        # Then: recover
        self.mock_client.check_health.side_effect = None
        self.mock_client.check_health.return_value = {"status": "ok"}
        transitions = self.monitor.run_all_checks()
        assert len(transitions) == 1
        assert transitions[0][0] == "backend_api"
        assert transitions[0][1] == HealthStatus.DOWN  # old
        assert transitions[0][2] == HealthStatus.HEALTHY  # new

    def test_no_duplicate_transition_on_repeated_failure(self):
        self.mock_client.check_health.side_effect = ApiConnectionError("timeout")
        self.mock_client.get_version.return_value = {"app_version": "1.0"}
        self.monitor.run_all_checks()  # first failure → transition
        transitions = self.monitor.run_all_checks()  # second failure → no transition
        assert transitions == []


# --- Alert delivery tests (Task 2) ---


class TestAlertDelivery:
    def setup_method(self):
        self.mock_client = MagicMock()
        self.mock_slack_client = MagicMock()
        self.monitor = HealthMonitor(
            api_client=self.mock_client,
            slack_client=self.mock_slack_client,
            alert_user_id="U12345",
            interval=60,
        )

    def test_send_alert_calls_slack(self):
        self.monitor.send_alert("backend_api", "Connection timeout", "Check if lenie-ai-server container is running")
        self.mock_slack_client.chat_postMessage.assert_called_once()
        call_kwargs = self.mock_slack_client.chat_postMessage.call_args[1]
        assert call_kwargs["channel"] == "U12345"
        assert "backend_api" in call_kwargs["text"]
        assert "Connection timeout" in call_kwargs["text"]

    def test_send_recovery_calls_slack(self):
        self.monitor.send_recovery("backend_api", 120.0)
        self.mock_slack_client.chat_postMessage.assert_called_once()
        call_kwargs = self.mock_slack_client.chat_postMessage.call_args[1]
        assert call_kwargs["channel"] == "U12345"
        assert "backend_api" in call_kwargs["text"]
        assert "recover" in call_kwargs["text"].lower() or "back" in call_kwargs["text"].lower()

    def test_alert_deduplication_via_run_all_checks(self):
        """Verify that repeated failures only trigger one alert."""
        self.mock_client.check_health.side_effect = ApiConnectionError("timeout")
        self.mock_client.get_version.return_value = {"app_version": "1.0"}

        # First failure → transition → alert sent
        transitions = self.monitor.run_all_checks()
        self.monitor.process_transitions(transitions)
        assert self.mock_slack_client.chat_postMessage.call_count == 1

        # Second failure → no transition → no additional alert
        transitions = self.monitor.run_all_checks()
        assert transitions == []
        self.monitor.process_transitions(transitions)
        assert self.mock_slack_client.chat_postMessage.call_count == 1  # still 1

    def test_recovery_notification_after_failure(self):
        """Full cycle: healthy → down → healthy triggers alert then recovery."""
        # Go down
        self.mock_client.check_health.side_effect = ApiConnectionError("timeout")
        self.mock_client.get_version.return_value = {"app_version": "1.0"}
        transitions = self.monitor.run_all_checks()
        self.monitor.process_transitions(transitions)
        assert self.mock_slack_client.chat_postMessage.call_count == 1  # alert

        # Recover
        self.mock_client.check_health.side_effect = None
        self.mock_client.check_health.return_value = {"status": "ok"}
        transitions = self.monitor.run_all_checks()
        self.monitor.process_transitions(transitions)
        assert self.mock_slack_client.chat_postMessage.call_count == 2  # alert + recovery

    def test_send_alert_handles_slack_error(self):
        """Alert delivery failure doesn't crash the monitor."""
        self.mock_slack_client.chat_postMessage.side_effect = Exception("Slack error")
        # Should not raise
        self.monitor.send_alert("backend_api", "timeout", "suggestion")

    def test_send_recovery_handles_slack_error(self):
        """Recovery delivery failure doesn't crash the monitor."""
        self.mock_slack_client.chat_postMessage.side_effect = Exception("Slack error")
        self.monitor.send_recovery("backend_api", 60.0)


# --- Scheduler tests (Task 3) ---


class TestScheduler:
    def setup_method(self):
        self.mock_client = MagicMock()
        self.mock_client.check_health.return_value = {"status": "ok"}
        self.mock_client.get_version.return_value = {"app_version": "1.0"}
        self.mock_slack_client = MagicMock()
        self.monitor = HealthMonitor(
            api_client=self.mock_client,
            slack_client=self.mock_slack_client,
            alert_user_id="U12345",
            interval=0.1,  # 100ms for test speed
        )

    def test_start_creates_daemon_timer(self):
        self.monitor.start()
        assert self.monitor._timer is not None
        assert self.monitor._timer.daemon is True
        self.monitor.stop()

    def test_stop_cancels_timer(self):
        self.monitor.start()
        self.monitor.stop()
        assert self.monitor._running is False

    def test_scheduler_runs_checks(self):
        """Verify scheduler actually executes health checks."""
        self.monitor.start()
        time.sleep(0.3)  # Let at least 1 check run
        self.monitor.stop()
        assert self.mock_client.check_health.call_count >= 1

    def test_double_start_is_safe(self):
        self.monitor.start()
        self.monitor.start()  # Should not crash or create duplicate timers
        self.monitor.stop()

    def test_double_stop_is_safe(self):
        self.monitor.start()
        self.monitor.stop()
        self.monitor.stop()  # Should not crash


# --- Graceful error handling tests (Task 1.6) ---


class TestGracefulErrorHandling:
    def setup_method(self):
        self.mock_client = MagicMock()
        self.mock_slack_client = MagicMock()
        self.monitor = HealthMonitor(
            api_client=self.mock_client,
            slack_client=self.mock_slack_client,
            alert_user_id="U12345",
            interval=60,
        )

    def test_check_backend_catches_connection_error(self):
        self.mock_client.check_health.side_effect = ConnectionError("refused")
        status, reason = self.monitor.check_backend_api()
        assert status == HealthStatus.DOWN

    def test_check_backend_catches_timeout(self):
        self.mock_client.check_health.side_effect = TimeoutError("timed out")
        status, reason = self.monitor.check_backend_api()
        assert status == HealthStatus.DOWN

    def test_check_db_catches_any_exception(self):
        self.mock_client.get_version.side_effect = Exception("unknown error")
        status, reason = self.monitor.check_database_connectivity()
        assert status == HealthStatus.DOWN

    def test_run_all_checks_never_raises(self):
        """Even if everything explodes, run_all_checks should not crash."""
        self.mock_client.check_health.side_effect = Exception("total failure")
        self.mock_client.get_version.side_effect = Exception("total failure")
        # Should not raise
        transitions = self.monitor.run_all_checks()
        assert isinstance(transitions, list)


# --- Interval validation tests (M2 fix) ---


class TestIntervalValidation:
    def test_zero_interval_raises(self):
        with pytest.raises(ValueError, match="positive"):
            HealthMonitor(
                api_client=MagicMock(),
                slack_client=MagicMock(),
                alert_user_id="U12345",
                interval=0,
            )

    def test_negative_interval_raises(self):
        with pytest.raises(ValueError, match="positive"):
            HealthMonitor(
                api_client=MagicMock(),
                slack_client=MagicMock(),
                alert_user_id="U12345",
                interval=-10,
            )


# --- Recovery downtime calculation tests (H1 fix) ---


class TestRecoveryDowntimeCalculation:
    def setup_method(self):
        self.mock_client = MagicMock()
        self.mock_slack_client = MagicMock()
        self.monitor = HealthMonitor(
            api_client=self.mock_client,
            slack_client=self.mock_slack_client,
            alert_user_id="U12345",
            interval=60,
        )

    def test_recovery_uses_down_since_for_downtime(self):
        """Recovery downtime should be calculated from down_since, not last_alert_sent."""
        down_time = datetime.now(tz=timezone.utc) - timedelta(minutes=10)

        # Simulate a transition from DOWN → HEALTHY with known down_since
        transitions = [("backend_api", HealthStatus.DOWN, HealthStatus.HEALTHY, None, down_time)]
        self.monitor.process_transitions(transitions)

        call_kwargs = self.mock_slack_client.chat_postMessage.call_args[1]
        # Downtime should be ~10 minutes, not 0
        assert "10m" in call_kwargs["text"]

    def test_recovery_with_no_down_since_uses_zero(self):
        """If down_since is None, downtime should be 0."""
        transitions = [("backend_api", HealthStatus.DOWN, HealthStatus.HEALTHY, None, None)]
        self.monitor.process_transitions(transitions)

        call_kwargs = self.mock_slack_client.chat_postMessage.call_args[1]
        assert "0s" in call_kwargs["text"]
