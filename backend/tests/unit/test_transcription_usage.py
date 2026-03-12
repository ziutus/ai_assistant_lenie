"""Tests for transcription usage summary aggregation logic.

Tests the pure aggregation logic extracted from TranscriptionLog.get_usage_summary()
without importing SQLAlchemy models (not available in lightweight test env).
"""


def _run_summary(rows):
    """Simulate TranscriptionLog.get_usage_summary aggregation logic.

    This mirrors the exact logic in TranscriptionLog.get_usage_summary()
    from library.db.models, tested without SQLAlchemy dependency.
    """
    total_spent = 0.0
    total_seconds = 0
    total_count = 0
    by_provider = {}

    for row in rows:
        spent = float(row.get("spent_usd", 0))
        seconds = int(row.get("total_seconds", 0))
        count = int(row.get("count", 0))
        total_spent += spent
        total_seconds += seconds
        total_count += count
        by_provider[row["provider"]] = {
            "spent_usd": round(spent, 4),
            "minutes": seconds // 60,
            "count": count,
        }

    return {
        "total_spent_usd": round(total_spent, 4),
        "total_seconds": total_seconds,
        "total_minutes": total_seconds // 60,
        "transactions_count": total_count,
        "by_provider": by_provider,
    }


class TestGetUsageSummary:
    def test_empty_table_returns_zeros(self):
        result = _run_summary([])
        assert result["total_spent_usd"] == 0.0
        assert result["total_seconds"] == 0
        assert result["total_minutes"] == 0
        assert result["transactions_count"] == 0
        assert result["by_provider"] == {}

    def test_single_provider(self):
        rows = [{"provider": "assemblyai", "spent_usd": 3.24, "total_seconds": 97200, "count": 12}]
        result = _run_summary(rows)
        assert result["total_spent_usd"] == 3.24
        assert result["total_seconds"] == 97200
        assert result["total_minutes"] == 1620
        assert result["transactions_count"] == 12
        assert result["by_provider"]["assemblyai"]["spent_usd"] == 3.24
        assert result["by_provider"]["assemblyai"]["count"] == 12

    def test_multiple_providers(self):
        rows = [
            {"provider": "assemblyai", "spent_usd": 2.0, "total_seconds": 60000, "count": 5},
            {"provider": "openai", "spent_usd": 1.0, "total_seconds": 30000, "count": 3},
        ]
        result = _run_summary(rows)
        assert result["total_spent_usd"] == 3.0
        assert result["total_seconds"] == 90000
        assert result["transactions_count"] == 8
        assert "assemblyai" in result["by_provider"]
        assert "openai" in result["by_provider"]

    def test_balance_calculation(self):
        rows = [{"provider": "assemblyai", "spent_usd": 3.24, "total_seconds": 97200, "count": 12}]
        summary = _run_summary(rows)
        balance_initial = 50.00
        balance_remaining = round(balance_initial - summary["total_spent_usd"], 4)
        assert balance_remaining == 46.76

    def test_balance_with_zero_usage(self):
        summary = _run_summary([])
        balance_initial = 50.00
        balance_remaining = round(balance_initial - summary["total_spent_usd"], 4)
        assert balance_remaining == 50.00

    def test_minutes_truncates_not_rounds(self):
        """59 seconds = 0 minutes (integer division)."""
        rows = [{"provider": "assemblyai", "spent_usd": 0.01, "total_seconds": 59, "count": 1}]
        result = _run_summary(rows)
        assert result["total_minutes"] == 0
        assert result["by_provider"]["assemblyai"]["minutes"] == 0
