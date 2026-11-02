import tkinter as tk
import unittest
from datetime import date
from unittest.mock import patch

from marketing_calendar.frontend import FrontendApp
from marketing_calendar.frontend_service import ProgressEvent


class FrontendUiTests(unittest.TestCase):
    def setUp(self):
        try:
            self.root = tk.Tk()
        except tk.TclError as exc:
            self.skipTest(f"没有可用的图形显示：{exc}")
        self.app = FrontendApp(self.root)
        self.root.update()

    def tearDown(self):
        if hasattr(self, "root"):
            self.root.destroy()

    def test_first_report_completion_is_not_whole_task_completion(self):
        self.app._on_progress(ProgressEvent("complete", "计划报表完成", "plan"))
        self.assertEqual(self.app.status_vars["plan"].get(), "已完成")
        self.assertEqual(self.app.headline_var.get(), "正在运行")

    def test_result_area_is_reachable_in_standard_window(self):
        self.assertEqual(self.root.winfo_height(), 710)
        self.assertTrue(self.app.open_excel_button.winfo_ismapped())

    def test_default_date_button_restores_agreed_period(self):
        self.app.start_var.set("2026-01-01")
        self.app.end_var.set("2026-01-02")
        with patch("marketing_calendar.frontend.ReportDateRange.default_for") as default_for:
            default_for.return_value = type("Period", (), {"start": date(2026, 9, 1), "end": date(2026, 10, 20)})()
            self.app._apply_default_dates()
        self.assertEqual(self.app.start_var.get(), "2026-09-01")
        self.assertEqual(self.app.end_var.get(), "2026-10-20")


if __name__ == "__main__":
    unittest.main()
