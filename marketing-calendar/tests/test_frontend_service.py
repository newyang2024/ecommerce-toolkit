import json
import tempfile
import unittest
from dataclasses import replace
from datetime import date
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from marketing_calendar.config import PathConfig, load_config
from marketing_calendar.frontend_service import (
    REPORTS,
    inspect_run,
    list_runs,
    run_pipeline,
)


class FrontendServiceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.run = self.root / "20261020T120000_20260901_20261019"
        self.run.mkdir()
        self.base = self.root / "base.xlsx"
        self.base.write_bytes(b"base-input")

    def _manifest(self, planned=REPORTS, completed=REPORTS):
        data = {
            "run_id": self.run.name,
            "date_range": {"start_date": "2026-09-01", "end_date": "2026-10-19"},
            "planned_reports": list(planned),
            "reports": [
                {"report_key": key, "files": [{"data_row_count": 10}]}
                for key in completed
            ],
        }
        (self.run / "manifest.json").write_text(json.dumps(data), encoding="utf-8")

    def test_result_summary_is_read_only(self):
        self._manifest()
        result = self.run / "万相台日报表_20261019_整理.xlsx"
        result.write_bytes(b"existing-result")
        before = result.read_bytes()
        summary = inspect_run(self.run)
        self.assertTrue(summary.is_download_complete)
        self.assertEqual(summary.row_counts["plan"], 10)
        self.assertEqual(summary.workbook, result)
        self.assertEqual(len(list_runs(self.root)), 1)
        self.assertEqual(result.read_bytes(), before)

    def test_completed_resume_does_not_open_browser_or_rewrite_result(self):
        self._manifest()
        result = self.run / "万相台日报表_20261019_整理.xlsx"
        result.write_bytes(b"existing-result")
        events = []
        with patch("marketing_calendar.browser.BrowserManager") as browser:
            summary = run_pipeline(
                base_workbook=self.base,
                output_root=self.root,
                resume_run=self.run,
                emit=events.append,
            )
        browser.assert_not_called()
        self.assertEqual(result.read_bytes(), b"existing-result")
        self.assertEqual(summary.workbook, result)
        self.assertEqual(events[-1].phase, "complete")

    def test_partial_report_run_cannot_be_merged_in_gui(self):
        self._manifest(planned=("plan",), completed=("plan",))
        with self.assertRaisesRegex(ValueError, "五表齐全"):
            run_pipeline(
                base_workbook=self.base,
                output_root=self.root,
                resume_run=self.run,
            )

    def test_resume_cannot_change_frozen_dates(self):
        self._manifest()
        with self.assertRaisesRegex(ValueError, "不能重新指定日期"):
            run_pipeline(
                base_workbook=self.base,
                output_root=self.root,
                resume_run=self.run,
                start_date=date(2026, 9, 1),
            )

    def test_new_flow_connects_download_and_merge_without_changing_inputs(self):
        config = replace(
            load_config(),
            paths=PathConfig(self.root / "runs", self.root / "logs", self.root / "profile"),
        )
        events = []
        base_before = self.base.read_bytes()

        def fake_download(_page, _config, archive, _period, reports, progress):
            manifest_path = archive.root / "manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["reports"] = [
                {"report_key": key, "files": [{"data_row_count": 10}]}
                for key in reports
            ]
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            for key in reports:
                progress(key, "complete", "下载完成")
            return manifest_path

        def fake_prepare(_base, _csv, output, **_kwargs):
            return SimpleNamespace(output=output)

        def fake_build(plan, *, latest_date, progress):
            self.assertEqual(latest_date, date(2026, 10, 19))
            progress(100, "整理完成")
            plan.output.write_bytes(b"new-workbook")
            return plan.output

        with (
            patch("marketing_calendar.browser.BrowserManager") as browser_class,
            patch("marketing_calendar.logging_setup.configure_logging"),
            patch("marketing_calendar.frontend_service.run_download", side_effect=fake_download),
            patch("marketing_calendar.frontend_service.prepare_merge", side_effect=fake_prepare),
            patch("marketing_calendar.frontend_service.build_merged_workbook", side_effect=fake_build),
        ):
            browser = browser_class.return_value.__enter__.return_value
            browser.wait_for_manual_login.return_value.logged_in = True
            summary = run_pipeline(
                base_workbook=self.base,
                config=config,
                start_date=date(2026, 9, 1),
                end_date=date(2026, 10, 19),
                emit=events.append,
            )
        self.assertEqual(summary.workbook.read_bytes(), b"new-workbook")
        self.assertEqual(len(summary.completed), 5)
        self.assertEqual(events[-1].phase, "complete")
        self.assertEqual(self.base.read_bytes(), base_before)


if __name__ == "__main__":
    unittest.main()
