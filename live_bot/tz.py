"""Thai timezone utilities — single source of truth."""
from datetime import datetime, date, timezone, timedelta

_THAI_TZ = timezone(timedelta(hours=7))


def thai_today() -> date:
    """Today's date in Thai timezone (UTC+7)."""
    return datetime.now(_THAI_TZ).date()


def thai_now() -> datetime:
    """Current datetime in Thai timezone (UTC+7)."""
    return datetime.now(_THAI_TZ)


THAI_TZ = _THAI_TZ  # public alias
