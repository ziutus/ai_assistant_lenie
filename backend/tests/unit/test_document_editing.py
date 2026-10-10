from unittest.mock import MagicMock

from library.document_editing import reopen_document_for_editing


def test_reopen_invalidates_derived_rows_and_resets_status():
    session = MagicMock()
    document = MagicMock(id=42)
    session.get.return_value = document
    session.scalar.return_value = None
    session.execute.return_value.rowcount = 2

    result = reopen_document_for_editing(session, 42)

    assert len(result["removed"]) == 15
    assert "document_organizations" in result["removed"]
    assert set(result["removed"].values()) == {2}
    assert document.processing_status == "NEED_CLEAN_MD"
    assert document.processing_error_code is None
    session.commit.assert_called_once()


def test_reopen_clears_place_tags_and_ner_markers_but_keeps_other_tags():
    session = MagicMock()
    document = MagicMock(id=42, tags="ekonomia,miejsce-aden,kraj-jemen, miejsce-rijad ,wojna")
    document.entities_checked_at = "2026-10-10"
    document.ner_unavailable_at = "2026-10-10"
    session.get.return_value = document
    session.scalar.return_value = None
    session.execute.return_value.rowcount = 0

    result = reopen_document_for_editing(session, 42)

    assert document.tags == "ekonomia,kraj-jemen,wojna"
    assert document.entities_checked_at is None
    assert document.ner_unavailable_at is None
    assert result["place_tags_removed"] == 2


def test_reopen_handles_document_without_tags():
    session = MagicMock()
    document = MagicMock(id=42, tags=None)
    session.get.return_value = document
    session.scalar.return_value = None
    session.execute.return_value.rowcount = 0

    assert reopen_document_for_editing(session, 42)["place_tags_removed"] == 0
    assert document.tags == ""


def test_reopen_refuses_while_analysis_is_active():
    session = MagicMock()
    session.get.return_value = MagicMock(id=42)
    session.scalar.return_value = MagicMock(status="running")

    try:
        reopen_document_for_editing(session, 42)
    except RuntimeError as exc:
        assert "still running" in str(exc)
    else:
        raise AssertionError("Expected active analysis to block reopening")

    session.execute.assert_not_called()
