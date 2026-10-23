"""Inspect emitted migration SQL without connecting to a database."""

import importlib.util
from pathlib import Path
from unittest.mock import patch


def test_missing_prices_migration():
    path = Path(__file__).resolve().parents[2] / "alembic/versions/d4a7c1e9b6f2_add_missing_llm_prices.py"
    spec = importlib.util.spec_from_file_location("missing_prices", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.revision == "d4a7c1e9b6f2"
    assert module.down_revision == "c2e8a5d1f9b3"
    versions = ["openai-gpt-4o-mini-2026-07-18", "cloudferro-gemma-4-31b-2026-07-18",
                "cloudferro-mistral-small-4-2026-07-18"]
    with patch.object(module.op, "execute") as execute:
        module.upgrade()
        sql = " ".join(call.args[0] for call in execute.call_args_list)
        assert all(version in sql for version in versions)
        assert all(value in sql for value in ("0.15", "0.60", "0.25", "0.50", "0.55", "USD", "EUR"))
        assert "WHERE NOT EXISTS" in sql and "existing.effective_to IS NULL" in sql
        assert "DATE '2026-07-18'" in sql
        execute.reset_mock()
        module.downgrade()
        statements = [call.args[0] for call in execute.call_args_list]
        assert len(statements) == 2
        assert statements[0].startswith("UPDATE llm_usage_logs SET pricing_version = NULL")
        assert statements[1].startswith("DELETE FROM llm_pricing WHERE pricing_version IN")
        assert all(version in statement for version in versions for statement in statements)
