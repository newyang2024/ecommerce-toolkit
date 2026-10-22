import io
import tempfile
import unittest
import xml.etree.ElementTree as ET
from datetime import date
from pathlib import Path

from marketing_calendar.data_merge import (
    EXTRA_HEADERS,
    MergeError,
    _add_extra_headers,
    _audit_csv,
    _next_row,
    _replace_row,
    _require_full_calculation,
)


class DataMergeTests(unittest.TestCase):
    def test_row_replaces_raw_data_but_preserves_formula(self):
        old = (
            b'<row r="2" hidden="1" spans="1:100">'
            b'<c r="A2" t="str"><f>VLOOKUP($S2,Match!A:B,2,0)</f><v>old</v></c>'
            b'<c r="S2" s="9"><v>123</v></c>'
            b'<c r="V2" s="9"><v>12</v></c></row>'
        )
        values = {19: ("内容名称", "主体ID"), 22: ("17", "展现量")}
        result = ET.fromstring(_replace_row(old, 2, values, 12, 22))
        self.assertNotIn("hidden", result.attrib)
        self.assertIsNone(result.find('c[@r="A2"]/v'))
        self.assertEqual(result.find('c[@r="S2"]/is/t').text, "内容名称")
        self.assertEqual(result.find('c[@r="V2"]/v').text, "17")

    def test_numeric_and_long_id_are_distinguished(self):
        old = b'<row r="2"><c r="A2"><f>S2</f><v>old</v></c></row>'
        values = {19: ("4290681686450271", "主体ID"), 22: ("1.25", "花费")}
        result = ET.fromstring(_replace_row(old, 2, values, 12, 22))
        self.assertEqual(result.find('c[@r="S2"]/is/t').text, "4290681686450271")
        self.assertEqual(result.find('c[@r="V2"]/v').text, "1.25")

    def test_new_headers_are_added_without_shifting_old_header(self):
        old = b'<row r="1"><c r="CR1" s="7" t="inlineStr"><is><t>old</t></is></c></row>'
        result = ET.fromstring(_add_extra_headers(old))
        self.assertEqual(result.find('c[@r="CR1"]/is/t').text, "old")
        self.assertEqual(result.find('c[@r="CS1"]/is/t').text, EXTRA_HEADERS[0])
        self.assertEqual(result.find('c[@r="CV1"]/is/t').text, EXTRA_HEADERS[-1])

    def test_row_stream_handles_self_closing_cells(self):
        source = io.BytesIO(b'<row r="2"><c r="A2"/><c r="B2"><v>1</v></c></row></sheetData>')
        row, remainder = _next_row(source, b"")
        self.assertTrue(row.endswith(b"</row>"))
        self.assertEqual(remainder, b"</sheetData>")

    def test_full_recalculation_is_requested(self):
        data = b'<workbook><calcPr calcId="191029"/></workbook>'
        result = _require_full_calculation(data)
        self.assertIn(b'fullCalcOnLoad="1"', result)
        self.assertIn(b'forceFullCalc="1"', result)

    def test_csv_date_window_is_not_hardcoded(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "report.csv"
            path.write_text("日期,展现量\n2026-10-18,1\n2026-10-19,2\n", encoding="gb18030")
            audit = _audit_csv("test", path, date(2026, 10, 18), date(2026, 10, 19))
            self.assertEqual(audit.row_count, 2)
            with self.assertRaises(MergeError):
                _audit_csv("test", path, date(2026, 10, 17), date(2026, 10, 19))


if __name__ == "__main__":
    unittest.main()
