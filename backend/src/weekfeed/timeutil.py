"""Timestamp helpers. Every stored timestamp goes through iso() so the strings sort chronologically."""
from __future__ import annotations

from datetime import datetime, timezone


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
