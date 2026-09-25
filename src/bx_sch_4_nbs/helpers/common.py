import re
from datetime import UTC, datetime

INSTAGRAM_PATTERN = re.compile(r"[a-z0-9._]{1,30}")


def normalize_instagram(handle: str) -> str:
    return handle.strip().lstrip("@").lower()


def utc_now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def parse_instagram(handle: str) -> str:
    normalized = normalize_instagram(handle)
    if not INSTAGRAM_PATTERN.fullmatch(normalized):
        raise ValueError("Invalid Instagram handle")
    return normalized


def mask_email(email: str) -> str:
    local, _, domain = email.partition("@")
    return f"{local[0]}***@{domain}"
