import re
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from bx_sch_4_nbs.config import settings

INSTAGRAM_PATTERN = re.compile(r"[a-z0-9._]{1,30}")
APPOINTMENTS_TZ = ZoneInfo(settings.appointments_timezone)


def normalize_instagram(handle: str) -> str:
    return handle.strip().lstrip("@").lower()


def utc_now() -> datetime:
    # Whole seconds only: MySQL DATETIME has no fractional seconds, so the value kept in Python
    # must match exactly what gets stored (MySQL would otherwise round the fraction).
    return datetime.now(UTC).replace(tzinfo=None, microsecond=0)


def parse_instagram(handle: str) -> str:
    normalized = normalize_instagram(handle)
    if not INSTAGRAM_PATTERN.fullmatch(normalized):
        raise ValueError("Invalid Instagram handle")
    return normalized


def mask_email(email: str) -> str:
    local, _, domain = email.partition("@")
    return f"{local[0]}***@{domain}"


def to_studio_time(value: datetime) -> datetime:
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(APPOINTMENTS_TZ)


def to_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        value = value.replace(tzinfo=APPOINTMENTS_TZ)
    return value.astimezone(UTC).replace(tzinfo=None)
