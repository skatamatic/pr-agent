"""
Unit tests for timezone_utils (used by cron, retention, and datetime handling).
"""
import pytest
from datetime import datetime, timezone, timedelta

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from timezone_utils import (
    utcnow_aware,
    ensure_timezone_aware,
    ensure_timezone_naive_utc,
    safe_datetime_compare,
    parse_datetime_safe,
    get_cutoff_datetime,
    format_datetime_for_db,
    get_minutes_since,
    to_utc_iso,
)


class TestTimezoneUtils:
    """Timezone helper functions."""

    def test_utcnow_aware_returns_aware(self):
        now = utcnow_aware()
        assert now.tzinfo is not None
        assert now.tzinfo.utcoffset(None) == timezone.utc.utcoffset(None)

    def test_ensure_timezone_aware_none(self):
        assert ensure_timezone_aware(None) is None

    def test_ensure_timezone_aware_naive(self):
        naive = datetime(2024, 1, 15, 12, 0, 0)
        result = ensure_timezone_aware(naive)
        assert result.tzinfo is not None
        assert result.year == 2024 and result.month == 1 and result.day == 15

    def test_ensure_timezone_aware_already_aware(self):
        aware = datetime(2024, 1, 15, 12, 0, 0, tzinfo=timezone.utc)
        result = ensure_timezone_aware(aware)
        assert result.tzinfo is not None
        assert result == aware

    def test_ensure_timezone_naive_utc_none(self):
        assert ensure_timezone_naive_utc(None) is None

    def test_ensure_timezone_naive_utc_aware(self):
        aware = datetime(2024, 1, 15, 12, 0, 0, tzinfo=timezone.utc)
        result = ensure_timezone_naive_utc(aware)
        assert result.tzinfo is None
        assert result.year == 2024

    def test_safe_datetime_compare_none_returns_false(self):
        assert safe_datetime_compare(None, datetime.now(timezone.utc)) is False
        assert safe_datetime_compare(datetime.now(timezone.utc), None) is False
        assert safe_datetime_compare(None, None) is False

    def test_safe_datetime_compare_less_than(self):
        earlier = datetime(2024, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
        later = datetime(2024, 1, 2, 0, 0, 0, tzinfo=timezone.utc)
        assert safe_datetime_compare(earlier, later) is True
        assert safe_datetime_compare(later, earlier) is False

    def test_parse_datetime_safe_empty(self):
        assert parse_datetime_safe("") is None
        assert parse_datetime_safe(None) is None

    def test_parse_datetime_safe_iso(self):
        result = parse_datetime_safe("2024-01-15T12:00:00+00:00")
        assert result is not None
        assert result.year == 2024 and result.month == 1
        assert result.tzinfo is not None

    def test_parse_datetime_safe_z_suffix(self):
        result = parse_datetime_safe("2024-01-15T12:00:00Z")
        assert result is not None
        assert result.tzinfo is not None

    def test_get_cutoff_datetime(self):
        cutoff = get_cutoff_datetime(days=1, hours=2)
        assert cutoff.tzinfo is not None
        now = utcnow_aware()
        assert cutoff < now
        delta = now - cutoff
        assert delta >= timedelta(days=1, hours=2) - timedelta(seconds=5)
        assert delta <= timedelta(days=1, hours=2) + timedelta(seconds=5)

    def test_format_datetime_for_db(self):
        dt = datetime(2024, 1, 15, 12, 0, 0, tzinfo=timezone.utc)
        s = format_datetime_for_db(dt)
        assert "2024" in s and "01" in s
        assert "T" in s or " " in s

    def test_get_minutes_since_none(self):
        assert get_minutes_since(None) is None

    def test_get_minutes_since_past(self):
        past = utcnow_aware() - timedelta(minutes=10)
        mins = get_minutes_since(past)
        assert mins is not None
        assert 9 <= mins <= 11

    def test_to_utc_iso_none(self):
        assert to_utc_iso(None) is None

    def test_to_utc_iso_returns_string(self):
        dt = datetime(2024, 1, 15, 12, 0, 0, tzinfo=timezone.utc)
        s = to_utc_iso(dt)
        assert isinstance(s, str)
        assert "2024" in s
