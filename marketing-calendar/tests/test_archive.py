import tempfile
import unittest
from datetime import date, datetime
from pathlib import Path
from zipfile import ZipFile

from marketing_calendar.archive import (
    ArchiveError,
    append_manifest_report,
    create_run_archive,
    safe_download_path,
    safe_extract_zip,
    validate_csv_file,
    write_manifest,
)
from marketing_calendar.date_range import ReportDateRange


class ArchiveTests(unittest.TestCase):
    def setUp(self) -> None:
        self.range = ReportDateRange(date(2026, 9, 1), date(2026, 10, 18))

    def test_creates_isolated_run_directories(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            archive = create_run_archive(
                Path(temp), self.range, datetime(2026, 10, 19, 15, 50, 0)
            )
            self.assertEqual(archive.run_id, "20261019T155000_20260901_20261018")
            self.assertTrue(archive.raw.is_dir())
            self.assertTrue(archive.extracted.is_dir())
            self.assertTrue(archive.diagnostics.is_dir())

    def test_rejects_unsafe_download_file_name(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaises(ArchiveError):
                safe_download_path(Path(temp), "../unexpected.xlsx")

    def test_rejects_zip_path_traversal(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            archive = root / "unsafe.zip"
            with ZipFile(archive, "w") as source:
                source.writestr("../outside.txt", "not allowed")
            with self.assertRaisesRegex(ArchiveError, "越界路径"):
                safe_extract_zip(archive, root / "extracted", 1024)

    def test_extracts_valid_zip_in_destination(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            archive = root / "valid.zip"
            with ZipFile(archive, "w") as source:
                source.writestr("reports/plan.csv", "a,b\n1,2\n")
            extracted = safe_extract_zip(archive, root / "extracted", 1024)
            self.assertEqual(extracted, (root / "extracted" / "reports" / "plan.csv",))

    def test_validates_csv_structure(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            csv_file = Path(temp) / "report.csv"
            csv_file.write_text("日期,花费\n2026-10-18,10\n", encoding="utf-8")
            result = validate_csv_file(csv_file)
            self.assertEqual(result.column_count, 2)
            self.assertEqual(result.data_row_count, 1)

    def test_writes_manifest_once(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            archive = create_run_archive(Path(temp), self.range, datetime(2026, 10, 19))
            manifest = write_manifest(archive, {"reports": []})
            self.assertTrue(manifest.is_file())
            with self.assertRaises(ArchiveError):
                write_manifest(archive, {"reports": []})

    def test_appends_each_report_once(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            archive = create_run_archive(Path(temp), self.range, datetime(2026, 10, 19))
            write_manifest(archive, {"reports": []})
            append_manifest_report(archive, {"report_key": "plan"})
            with self.assertRaisesRegex(ArchiveError, "已包含"):
                append_manifest_report(archive, {"report_key": "plan"})


if __name__ == "__main__":
    unittest.main()
