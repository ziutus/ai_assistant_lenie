"""Expiry of feed items parked under the "Może kiedyś" priority.

An item saved for later with the lowest priority group (``priority_rank`` 100, the same rule the UI uses to
find the "Może kiedyś" button) loses its value with time. After a retention period counted from ``saved_at`` it
is moved to "skipped" with the review reason ``expired``. The period is a number of months chosen per topic
(``content_groups.retention_months``, e.g. a year for health or team management); an item with several topics
keeps the LONGEST one, a topic without a value falls back to a household default (``app_settings``, 6 months).
Items saved for later under any other priority, or without one, never expire.
"""

import calendar
import datetime as dt

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from library import app_settings
from library.db.models import FeedItem, FeedItemGroupMembership

MAYBE_LATER_PRIORITY_RANK = 100
SETTING_KEY = "feed_maybe_later_retention_months"
DEFAULT_MONTHS = 6
MIN_MONTHS, MAX_MONTHS = 1, 120
REVIEW_REASON = "expired"
LISTED_ITEMS = 50  # items named in a run result; the count is always complete


def valid_months(value) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and MIN_MONTHS <= value <= MAX_MONTHS


def default_months(session) -> int:
    saved = app_settings.get_setting(session, SETTING_KEY)
    return saved if valid_months(saved) else DEFAULT_MONTHS


def add_months(moment: dt.datetime, months: int) -> dt.datetime:
    """Calendar months later; a day that does not exist in the target month becomes that month's last day."""
    index = moment.year * 12 + moment.month - 1 + months
    year, month = divmod(index, 12)
    month += 1
    return moment.replace(year=year, month=month, day=min(moment.day, calendar.monthrange(year, month)[1]))


def _active_groups(item: FeedItem):
    return [membership.group for membership in item.group_memberships if membership.group.archived_at is None]


def is_maybe_later(item: FeedItem) -> bool:
    return any(group.kind == "priority" and group.priority_rank == MAYBE_LATER_PRIORITY_RANK for group in _active_groups(item))


def retention_months(item: FeedItem, default: int) -> int:
    values = [group.retention_months for group in _active_groups(item) if group.kind == "topic" and group.retention_months]
    return max(values) if values else default


def expiry(item: FeedItem, default: int) -> tuple[dt.datetime, int] | None:
    """``(expires_at, months)`` for an item that is saved under "Może kiedyś", else None."""
    if item.status != "saved_for_later" or item.saved_at is None or not is_maybe_later(item):
        return None
    months = retention_months(item, default)
    return add_months(item.saved_at, months), months


def expiry_fields(item: FeedItem, default: int) -> dict:
    result = expiry(item, default)
    return {"expires_at": result[0].isoformat() if result else None, "retention_months": result[1] if result else None}


def expire_saved_items(session, *, now: dt.datetime | None = None, dry_run: bool = False) -> dict:
    """Skip every "Może kiedyś" item whose retention period is over; ``dry_run`` only reports them."""
    from library.feed_monitor_service import transition_item

    now = now or dt.datetime.now(dt.timezone.utc)
    default = default_months(session)
    items = session.scalars(
        select(FeedItem).where(FeedItem.status == "saved_for_later", FeedItem.saved_at.is_not(None))
        .options(selectinload(FeedItem.group_memberships).selectinload(FeedItemGroupMembership.group))
        .order_by(FeedItem.saved_at)
    ).all()
    due = []
    for item in items:
        result = expiry(item, default)
        if result is not None and result[0] <= now:
            due.append((item, *result))
    listed = [
        {"id": item.id, "title": item.title, "saved_at": item.saved_at.isoformat(), "expires_at": expires_at.isoformat(), "months": months}
        for item, expires_at, months in due[:LISTED_ITEMS]
    ]
    due_ids = [item.id for item, _, _ in due]  # read before the first commit expires the loaded rows
    expired, failed = 0, []
    if not dry_run:
        for item_id in due_ids:
            try:
                transition_item(session, item_id, "skipped", review_reason=REVIEW_REASON)
                expired += 1
            except (RuntimeError, ValueError) as exc:  # moved by someone else in the meantime: leave it alone
                session.rollback()
                failed.append({"id": item_id, "error": str(exc)})
    return {"dry_run": dry_run, "due": len(due), "expired": expired, "failed": failed, "default_months": default, "items": listed}
