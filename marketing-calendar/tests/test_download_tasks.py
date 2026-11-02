import unittest
from datetime import date, datetime

from marketing_calendar.date_range import ReportDateRange
from marketing_calendar.download_tasks import (
    DownloadTask,
    DownloadTaskError,
    match_new_task,
    new_tasks_since,
    task_baseline,
)


def task(task_id: str, file_name: str, date_range: str, created_date: str) -> DownloadTask:
    return DownloadTask(
        task_id=task_id,
        status="生成成功",
        file_name=file_name,
        attribution_period="15天累计数据",
        date_range=date_range,
        created_date=created_date,
    )


class DownloadTaskTests(unittest.TestCase):
    def setUp(self) -> None:
        self.date_range = ReportDateRange(date(2026, 9, 1), date(2026, 10, 18))
        self.submitted_at = datetime(2026, 10, 19, 9, 49, 39)

    def test_baseline_excludes_existing_tasks(self) -> None:
        old = task("old", "计划报表_20261019_093550", "2026-09-01至2026-10-18", "2026-10-19")
        new = task("new", "计划报表_20261019_094939", "2026-09-01至2026-10-18", "2026-10-19")
        self.assertEqual(task_baseline([old]), frozenset({"old"}))
        self.assertEqual(new_tasks_since({"old"}, [new, old]), (new,))

    def test_match_requires_new_task_to_match_all_known_fields(self) -> None:
        candidate = task("new", "计划报表_20261019_094939", "2026-09-01至2026-10-18", "2026-10-19")
        self.assertEqual(
            match_new_task([candidate], "plan", self.date_range, self.submitted_at),
            candidate,
        )

    def test_match_rejects_ambiguous_candidates(self) -> None:
        candidates = [
            task("one", "计划报表_20261019_094939", "2026-09-01至2026-10-18", "2026-10-19"),
            task("two", "计划报表_20261019_094940", "2026-09-01至2026-10-18", "2026-10-19"),
        ]
        with self.assertRaisesRegex(DownloadTaskError, "无法唯一匹配"):
            match_new_task(candidates, "plan", self.date_range, self.submitted_at)

    def test_match_rejects_historical_task_with_different_date(self) -> None:
        historical = task("old", "计划报表_20261016_175024", "2026-09-01至2026-10-15", "2026-10-16")
        with self.assertRaisesRegex(DownloadTaskError, "匹配数=0"):
            match_new_task([historical], "plan", self.date_range, self.submitted_at)


if __name__ == "__main__":
    unittest.main()
