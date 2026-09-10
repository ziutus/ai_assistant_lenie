"""Struktura fixtury oraz deterministyczny eksport bez żywej bazy."""

import datetime
import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

pytest.importorskip("sqlalchemy")

from imports import dump_cleanup_rules as dump
from scripts import review_removed_lines as review
from library.db.models import DocumentRemovedLine


def test_fixture_structure():
    path = Path(__file__).resolve().parents[1] / "fixtures" / "cleanup_rules.json"
    assert path.is_file()
    rows = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(rows, list)
    for row in rows:
        assert isinstance(row, dict)
        assert {"scope", "match_type", "pattern", "active"} <= row.keys()


def test_dump_roundtrip(monkeypatch, tmp_path):
    session = MagicMock()
    session.execute.return_value.mappings.return_value = [
        {"id": 1, "pattern": "Zażółć", "created_at": datetime.datetime(2026, 9, 10)},
    ]
    monkeypatch.setattr(dump, "get_session", lambda: session)
    out = tmp_path / "rules.json"
    monkeypatch.setattr("sys.argv", ["dump_cleanup_rules.py", "--out", str(out)])
    dump.main()
    content = out.read_text(encoding="utf-8")
    assert "Zażółć" in content
    assert content.index('"created_at"') < content.index('"id"') < content.index('"pattern"')
    assert json.loads(content)[0]["created_at"] == "2026-09-10 00:00:00"
    assert str(session.execute.call_args.args[0]) == "SELECT * FROM cleanup_rules ORDER BY id"
    session.close.assert_called_once()


def test_promote_cli(monkeypatch, capsys):
    session = MagicMock()
    source = DocumentRemovedLine(id=7, review_status="pending")
    session.get.return_value = source
    session.flush.side_effect = lambda: setattr(session.add.call_args.args[0], "id", 42)
    monkeypatch.setattr(review, "get_session", lambda: session)
    monkeypatch.setattr("sys.argv", [
        "review_removed_lines.py", "--promote-rule", "--removed-line-id", "7", "--scope", "domain",
        "--domain", "www.onet.pl", "--match-type", "literal_line", "--pattern", "Zajrzyj na nasz profil",
    ])
    review.main()
    assert capsys.readouterr().out.strip() == "cleanup_rules:42"
    rule = session.add.call_args.args[0]
    assert rule.created_by == "review_removed_lines"
    assert rule.domain == "onet.pl"
    assert rule.source_removed_line_id == 7
    assert source.rule_reference == "cleanup_rules:42"
    assert source.review_status == "rule_added"
    assert source.reviewed_at is not None
    session.commit.assert_called_once()
    session.close.assert_called_once()


def test_promote_cli_requires_domain(monkeypatch):
    factory = MagicMock()
    monkeypatch.setattr(review, "get_session", factory)
    monkeypatch.setattr("sys.argv", [
        "review_removed_lines.py", "--promote-rule", "--removed-line-id", "7", "--scope", "domain",
        "--match-type", "literal_line", "--pattern", "Zajrzyj na nasz profil",
    ])
    with pytest.raises(SystemExit) as error:
        review.main()
    assert error.value.code == 2
    factory.assert_not_called()
