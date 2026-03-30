"""Context manager for tracking import script operations in the import_logs table.

Usage:
    session = get_session()
    with ImportLogTracker("dynamodb_sync", session, {"since": "2026-03-01"}) as tracker:
        tracker.set_dates(since_date=date(2026, 3, 1))
        # ... do import work ...
        tracker.set_counts(found=100, added=50, skipped=45, error=5)
    # On exit: status='success', finished_at=now(), committed
"""

from datetime import date, datetime, timezone

from library.db.engine import get_session
from library.db.models import ImportLog


class ImportLogTracker:
    """Track an import run in the import_logs table.

    Uses a dedicated session for the log row, independent of the main script
    session. This ensures that the log is committed even if the main session
    has uncommitted work or is in a failed state.
    """

    def __init__(self, script_name: str, parameters: dict | None = None):
        self._log_session = get_session()
        self.log = ImportLog(
            script_name=script_name,
            parameters=parameters or {},
        )

    def __enter__(self) -> "ImportLogTracker":
        self._log_session.add(self.log)
        self._log_session.flush()
        return self

    def set_counts(self, found: int = 0, added: int = 0, skipped: int = 0, error: int = 0) -> None:
        self.log.items_found = found
        self.log.items_added = added
        self.log.items_skipped = skipped
        self.log.items_error = error

    def set_dates(self, since_date: date | None = None, until_date: date | None = None) -> None:
        self.log.since_date = since_date
        self.log.until_date = until_date

    def add_note(self, note: str) -> None:
        if self.log.notes:
            self.log.notes += f"\n{note}"
        else:
            self.log.notes = note

    def __exit__(self, exc_type, exc_val, exc_tb) -> bool:
        self.log.finished_at = datetime.now(timezone.utc)
        if exc_type is None:
            self.log.status = "success"
        else:
            self.log.status = "error"
            self.log.error_message = str(exc_val)
        try:
            self._log_session.commit()
        except Exception:
            self._log_session.rollback()
        finally:
            self._log_session.close()
        return False  # Don't suppress exceptions
