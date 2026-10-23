"""Tiny key/value store (``app_settings``) for choices made in the UI, shared by the whole household."""

import datetime

from sqlalchemy.orm import Session

from library.db.models import AppSetting


def get_setting(session: Session, key: str, default=None):
    row = session.get(AppSetting, key)
    return default if row is None else row.value


def set_setting(session: Session, key: str, value) -> None:
    """Upsert ``key``; ``None`` removes it so the caller's built-in default applies again. Commits."""
    row = session.get(AppSetting, key)
    if value is None:
        if row is not None:
            session.delete(row)
    elif row is None:
        session.add(AppSetting(key=key, value=value))
    else:
        row.value = value
        row.updated_at = datetime.datetime.now(datetime.timezone.utc)
    session.commit()
