import re

INSTAGRAM_PATTERN = re.compile(r"[a-z0-9._]{1,30}")


def normalize_instagram(handle: str) -> str:
    return handle.strip().lstrip("@").lower()
