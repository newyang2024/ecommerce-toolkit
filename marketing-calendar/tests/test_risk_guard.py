import json
import tempfile
import unittest
from datetime import date, datetime
from pathlib import Path

from marketing_calendar.date_range import ReportDateRange
from marketing_calendar.download_tasks import DownloadTask, snapshot_download_tasks
from marketing_calendar.risk_guard import (
    ManualVerificationRequired,
    SubmissionJournal,
    SubmissionUncertain,
    assert_no_verification,
    resume_after_manual_verification,
    submit_once,
)


class _Dialog:
    def __init__(self, visible: bool):
        self.visible = visible

    def count(self) -> int:
        return 1

    def nth(self, index: int) -> "_Dialog":
        return self

    def is_visible(self) -> bool:
        return self.visible


class _Page:
    def __init__(self, verification_visible: bool = False):
        self.verification_visible = verification_visible

    def locator(self, selector: str) -> _Dialog:
        self.selector = selector
        return _Dialog(self.verification_visible)


class RiskGuardTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "submission_state.json"
        self.range = ReportDateRange(date(2026, 9, 1), date(2026, 10, 19))
        self.submitted_at = datetime(2026, 10, 20, 16, 32, 36)

    def test_visible_verification_requires_manual_action(self) -> None:
        with self.assertRaises(ManualVerificationRequired):
            assert_no_verification(_Page(True))
        with self.assertRaises(ManualVerificationRequired):
            snapshot_download_tasks(_Page(True))
        assert_no_verification(_Page(False))

    def test_pending_record_persists_and_blocks_duplicate_submit(self) -> None:
        journal = SubmissionJournal(self.path)
        called = []
        submit_once(
            _Page(), journal, "product", self.range, self.submitted_at,
            {"old"}, lambda: called.append("submitted"),
        )
        self.assertEqual(called, ["submitted"])
        self.assertEqual(SubmissionJournal(self.path).get("product").status, "pending")
        with self.assertRaises(SubmissionUncertain):
            submit_once(
                _Page(), journal, "product", self.range, self.submitted_at,
                {"old"}, lambda: called.append("duplicate"),
            )
        self.assertEqual(called, ["submitted"])

    def test_action_failure_stays_pending(self) -> None:
        journal = SubmissionJournal(self.path)

        def fail() -> None:
            raise TimeoutError("page result unknown")

        with self.assertRaises(SubmissionUncertain):
            submit_once(
                _Page(), journal, "product", self.range, self.submitted_at,
                {"old"}, fail,
            )
        self.assertEqual(journal.get("product").status, "pending")

    def test_verification_after_action_stays_pending(self) -> None:
        journal = SubmissionJournal(self.path)
        page = _Page()

        def trigger_verification() -> None:
            page.verification_visible = True

        with self.assertRaises(ManualVerificationRequired):
            submit_once(
                page, journal, "product", self.range, self.submitted_at,
                {"old"}, trigger_verification,
            )
        self.assertEqual(journal.get("product").status, "pending")

    def test_manual_resume_confirms_only_unique_new_task(self) -> None:
        journal = SubmissionJournal(self.path)
        journal.begin("product", self.range, self.submitted_at, {"old"})
        old = self._task("old")
        new = self._task("new")
        with self.assertRaises(ManualVerificationRequired):
            resume_after_manual_verification(_Page(True), journal, "product", [old, new])
        self.assertEqual(journal.get("product").status, "pending")
        with self.assertRaises(SubmissionUncertain):
            resume_after_manual_verification(_Page(), journal, "product", [old])
        self.assertEqual(journal.get("product").status, "pending")
        matched = resume_after_manual_verification(
            _Page(), journal, "product", [old, new]
        )
        self.assertEqual(matched.task_id, "new")
        self.assertEqual(journal.get("product").task_id, "new")
        self.assertEqual(journal.get("product").status, "confirmed")

    def test_corrupt_journal_never_allows_silent_retry(self) -> None:
        self.path.write_text(json.dumps({"version": 1, "records": []}), encoding="utf-8")
        with self.assertRaises(SubmissionUncertain):
            SubmissionJournal(self.path).begin(
                "product", self.range, self.submitted_at, set()
            )

    def _task(self, task_id: str) -> DownloadTask:
        return DownloadTask(
            task_id=task_id,
            status="生成成功",
            file_name="商品报表_20261020_163236",
            attribution_period="15天累计数据",
            date_range="2026-09-01至2026-10-19",
            created_date="2026-10-20",
        )


if __name__ == "__main__":
    unittest.main()
