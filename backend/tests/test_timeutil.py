from datetime import datetime, timedelta, timezone

import pytest

from weekfeed.timeutil import iso, local_date, local_minute, parse


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


def test_local_date_uses_the_local_day_not_the_utc_day():
    # 21:00 MDT on Oct 7 is 03:00 UTC on Oct 8
    assert local_date("2026-10-08T03:00:00.000000+00:00") == "2026-10-07"
    assert local_date("2026-10-08T03:00:00.000000+00:00", timezone.utc) == "2026-10-08"


def test_local_minute_formats_in_local_time():
    assert local_minute("2026-10-08T03:00:00.000000+00:00") == "2026-10-07 21:00"
