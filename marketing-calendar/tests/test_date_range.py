import unittest
from datetime import date, datetime, timezone

from marketing_calendar.date_range import DateRangeError, ReportDateRange


class ReportDateRangeTests(unittest.TestCase):
    def test_default_range_runs_from_previous_month_to_yesterday(self) -> None:
        value = ReportDateRange.default_for(date(2026, 10, 19))
        self.assertEqual(value.start, date(2026, 9, 1))
        self.assertEqual(value.end, date(2026, 10, 18))

    def test_default_range_handles_new_year(self) -> None:
        value = ReportDateRange.default_for(date(2026, 1, 1))
        self.assertEqual(value.start, date(2025, 12, 1))
        self.assertEqual(value.end, date(2025, 12, 31))

    def test_timezone_is_used_for_aware_datetime(self) -> None:
        value = ReportDateRange.default_for(
            datetime(2026, 10, 18, 17, 0, tzinfo=timezone.utc)
        )
        self.assertEqual(value.start, date(2026, 9, 1))
        self.assertEqual(value.end, date(2026, 10, 18))

    def test_explicit_dates_are_preserved(self) -> None:
        value = ReportDateRange.resolve(date(2026, 8, 1), date(2026, 8, 31))
        self.assertEqual(value.as_dict(), {"start_date": "2026-08-01", "end_date": "2026-08-31"})

    def test_partial_or_reversed_dates_fail(self) -> None:
        with self.assertRaises(DateRangeError):
            ReportDateRange.resolve(date(2026, 8, 1), None)
        with self.assertRaises(DateRangeError):
            ReportDateRange.resolve(date(2026, 8, 2), date(2026, 8, 1))
