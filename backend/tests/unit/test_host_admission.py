import datetime as dt
import json

from library.host_admission import HostAdmissionGate


def _snapshot(**overrides):
    values = {
        "collected_at": "2026-08-27T10:00:00Z", "load_1": 1.0,
        "mem_available_bytes": 3 * 1024**3, "swap_used_bytes": 0,
        "iowait_percent": 1.0, "disk_temperatures_c": [45.0],
    }
    values.update(overrides)
    return values


def _gate(tmp_path, **snapshot):
    path = tmp_path / "host-health.json"
    path.write_text(json.dumps(_snapshot(**snapshot)), encoding="utf-8")
    return HostAdmissionGate({"HOST_ADMISSION_ENABLED": "true", "HOST_HEALTH_PATH": str(path)})


NOW = dt.datetime(2026, 8, 27, 10, 0, 30, tzinfo=dt.timezone.utc)


def test_disabled_gate_allows_claim_without_snapshot():
    decision = HostAdmissionGate({}).evaluate()
    assert (decision.allowed, decision.reason, decision.sleep_seconds) == (True, "disabled", 0)


def test_disabled_gate_ignores_a_pressured_snapshot(tmp_path):
    path = tmp_path / "host-health.json"
    path.write_text(json.dumps(_snapshot(load_1=99.0)), encoding="utf-8")
    gate = HostAdmissionGate({"HOST_ADMISSION_ENABLED": "false", "HOST_HEALTH_PATH": str(path)})
    assert gate.evaluate(NOW).allowed is True


def test_enabled_gate_allows_claim_on_a_healthy_snapshot(tmp_path):
    decision = _gate(tmp_path).evaluate(NOW)
    assert (decision.allowed, decision.reason, decision.sleep_seconds) == (True, "healthy", 0)


def test_gate_defers_when_snapshot_is_missing(tmp_path):
    gate = HostAdmissionGate(
        {"HOST_ADMISSION_ENABLED": "true", "HOST_HEALTH_PATH": str(tmp_path / "missing")}
    )
    decision = gate.evaluate(NOW)
    assert (decision.allowed, decision.reason) == (False, "host_health_unavailable")
    assert decision.sleep_seconds == 60


def test_gate_defers_when_snapshot_is_not_valid_json(tmp_path):
    path = tmp_path / "host-health.json"
    path.write_text("{ this is not json", encoding="utf-8")
    gate = HostAdmissionGate({"HOST_ADMISSION_ENABLED": "true", "HOST_HEALTH_PATH": str(path)})
    assert (gate.evaluate(NOW).allowed, gate.evaluate(NOW).reason) == (False, "host_health_unavailable")


def test_gate_defers_when_snapshot_fields_are_the_wrong_type(tmp_path):
    decision = _gate(tmp_path, load_1="not-a-number").evaluate(NOW)
    assert (decision.allowed, decision.reason) == (False, "host_health_invalid")


def test_gate_defers_when_collected_at_is_missing(tmp_path):
    path = tmp_path / "host-health.json"
    payload = _snapshot()
    del payload["collected_at"]
    path.write_text(json.dumps(payload), encoding="utf-8")
    gate = HostAdmissionGate({"HOST_ADMISSION_ENABLED": "true", "HOST_HEALTH_PATH": str(path)})
    assert gate.evaluate(NOW).reason == "host_health_unavailable"


def test_gate_defers_when_snapshot_is_stale(tmp_path):
    decision = _gate(tmp_path).evaluate(dt.datetime(2026, 8, 27, 10, 3, tzinfo=dt.timezone.utc))
    assert (decision.allowed, decision.reason) == (False, "host_health_stale")


def test_gate_defers_on_each_pressure_signal(tmp_path):
    for override, reason in [
        ({"load_1": 2.6}, "load_1_high"),
        ({"mem_available_bytes": 1024}, "memory_low"),
        ({"swap_used_bytes": 300 * 1024**2}, "swap_high"),
        ({"iowait_percent": 16}, "iowait_high"),
        ({"disk_temperatures_c": [56]}, "disk_temperature_high"),
    ]:
        decision = _gate(tmp_path, **override).evaluate(NOW)
        assert (decision.allowed, decision.reason, decision.sleep_seconds) == (False, reason, 60)


def test_thresholds_are_configurable(tmp_path):
    path = tmp_path / "host-health.json"
    path.write_text(json.dumps(_snapshot(load_1=5.0)), encoding="utf-8")
    lenient = HostAdmissionGate(
        {"HOST_ADMISSION_ENABLED": "true", "HOST_HEALTH_PATH": str(path), "WORKER_LOAD_1_MAX": "8"}
    )
    assert lenient.evaluate(NOW).allowed is True
    strict = HostAdmissionGate(
        {
            "HOST_ADMISSION_ENABLED": "true", "HOST_HEALTH_PATH": str(path),
            "WORKER_LOAD_1_MAX": "4", "HOST_ADMISSION_THROTTLE_SECONDS": "30",
        }
    )
    decision = strict.evaluate(NOW)
    assert (decision.allowed, decision.reason, decision.sleep_seconds) == (False, "load_1_high", 30)
