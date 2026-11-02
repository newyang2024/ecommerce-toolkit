import io
import unittest
import xml.etree.ElementTree as ET
from zipfile import ZipFile

from marketing_calendar.matching_source import MAIN, _converted_sheet


class MatchingSourceTests(unittest.TestCase):
    def test_replaces_values_without_reusing_foreign_string_or_style_indexes(self):
        old_xml = (
            b'<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
            b'<dimension ref="A1:B2"/><sheetData>'
            b'<row r="1"><c r="A1" t="s"><v>0</v></c><c r="B1" t="s"><v>1</v></c></row>'
            b'<row r="2"><c r="A2" s="5" t="s"><v>2</v></c></row>'
            b'</sheetData><pageMargins left="0.7"/></worksheet>'
        )
        new_xml = (
            b'<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
            b'<dimension ref="A1:B3"/><sheetData>'
            b'<row r="1"><c r="A1" t="s"><v>1</v></c><c r="B1" t="s"><v>0</v></c></row>'
            b'<row r="2"><c r="A2" s="99" t="s"><v>2</v></c></row>'
            b'<row r="3"><c r="A3" s="100" t="s"><v>3</v></c></row>'
            b'</sheetData></worksheet>'
        )
        old = self._book(["主体ID", "简称", "旧值"])
        new = self._book(["简称", "主体ID", "新值", "新增记录"])
        with ZipFile(old) as template, ZipFile(new) as donor:
            result = _converted_sheet(old_xml, new_xml, template, donor)
        root = ET.fromstring(result)
        self.assertEqual(root.find(f"{MAIN}dimension").get("ref"), "A1:B3")
        self.assertEqual(root.find(f"{MAIN}sheetData/{MAIN}row[@r='2']/{MAIN}c/{MAIN}is/{MAIN}t").text, "新值")
        self.assertEqual(root.find(f"{MAIN}sheetData/{MAIN}row[@r='2']/{MAIN}c").get("s"), "5")
        self.assertEqual(root.find(f"{MAIN}sheetData/{MAIN}row[@r='3']/{MAIN}c").get("s"), "5")
        self.assertIsNotNone(root.find(f"{MAIN}pageMargins"))

    @staticmethod
    def _book(strings):
        buffer = io.BytesIO()
        with ZipFile(buffer, "w") as book:
            values = "".join(f"<si><t>{value}</t></si>" for value in strings)
            book.writestr("xl/sharedStrings.xml", f'<sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">{values}</sst>')
        buffer.seek(0)
        return buffer


if __name__ == "__main__":
    unittest.main()
