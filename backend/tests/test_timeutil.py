from datetime import datetime, timedelta, timezone

import pytest

from weekfeed.timeutil import iso, parse


def test_iso_normalizes_to_utc_with_microseconds():
    dt = datetime(2026, 10, 7, 9, 5, tzinfo=timezone(timedelta(hours=-6)))
    assert iso(dt) == "2026-10-07T15:05:00.000000+00:00"


def test_iso_strings_sort_chronologically():
    a = iso(datetime(2026, 10, 7, 23, 30, tzinfo=timezone(timedelta(hours=9))))
    b = iso(datetime(2026, 10, 7, 15, 0, tzinfo=timezone.utc))
    assert a < b  # 23:30 +09:00 is 14:30 UTC


def test_iso_rejects_naive_datetimes():
    with pytest.raises(ValueError):
        iso(datetime(2026, 1, 1))


def test_parse_round_trips_and_accepts_z_suffix():
    assert iso(parse("2026-10-07T15:05:00.000000+00:00")) == "2026-10-07T15:05:00.000000+00:00"
    assert iso(parse("2026-10-07T15:05:00.000Z")) == "2026-10-07T15:05:00.000000+00:00"
