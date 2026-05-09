from __future__ import annotations

from datetime import datetime


WINDOWS_ILLEGAL_CHARS = set('<>:"/\\|?*')

YEAR = "\u5e74"
MONTH = "\u6708"
DAY = "\u65e5"
HOUR = "\u65f6"
MINUTE = "\u5206"


def default_draft_name(now: datetime | None = None) -> str:
    current = now or datetime.now()
    return f"{current.year}{YEAR}{current.month}{MONTH}{current.day}{DAY}{current.hour}{HOUR}{current.minute}{MINUTE}"


def safe_draft_name(value: str | None, *, fallback: str | None = None) -> str:
    source = (value or "").strip()
    if not source:
        return fallback or default_draft_name()

    normalized: list[str] = []
    last_was_space = False
    for char in source:
        if char in WINDOWS_ILLEGAL_CHARS or ord(char) < 32:
            continue
        if char.isspace():
            if last_was_space:
                continue
            normalized.append(" ")
            last_was_space = True
            continue
        normalized.append(char)
        last_was_space = False

    cleaned = "".join(normalized).strip().rstrip(".")
    return cleaned or fallback or default_draft_name()
