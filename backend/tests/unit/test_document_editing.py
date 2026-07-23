from unittest.mock import MagicMock

from library.document_editing import reopen_document_for_editing


def test_reopen_invalidates_derived_rows_and_resets_status():
    session = MagicMock()
    document = MagicMock(id=42)
    session.get.return_value = document
    session.scalar.return_value = None
    session.execute.return_value.rowcount = 2

    result = reopen_document_for_editing(session, 42)

    assert len(result["removed"]) == 13
    assert set(result["removed"].values()) == {2}
    assert document.processing_status == "NEED_CLEAN_MD"
    assert document.processing_error_code is None
    session.commit.assert_called_once()


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
