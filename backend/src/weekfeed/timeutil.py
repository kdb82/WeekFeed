"""Timestamp helpers. Every stored timestamp goes through iso() so the strings sort chronologically.

Stored timestamps are UTC; anything shown to the user (or the model) is converted to local time first.
"""
from __future__ import annotations

from datetime import datetime, timezone, tzinfo


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def iso(dt: datetime) -> str:
    if dt.tzinfo is None:
        raise ValueError("iso() needs a timezone-aware datetime")
    return dt.astimezone(timezone.utc).isoformat(timespec="microseconds")


def parse(value: str) -> datetime:
    dt = datetime.fromisoformat(value)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def now_iso() -> str:
    return iso(utcnow())


def local_date(value: str, tz: tzinfo | None = None) -> str:
    """The calendar day of a stored timestamp in local time (or `tz`), as YYYY-MM-DD."""
    return parse(value).astimezone(tz).date().isoformat()


def local_minute(value: str, tz: tzinfo | None = None) -> str:
    return parse(value).astimezone(tz).strftime("%Y-%m-%d %H:%M")
