import unittest

from marketing_calendar.pivot_refresh import _POWERSHELL


class PivotRefreshScriptTests(unittest.TestCase):
    def test_blank_date_page_field_has_a_safe_unique_fallback(self):
        self.assertIn("if ($blankMatches.Count -eq 1)", _POWERSHELL)
        self.assertIn("唯一空白页筛选字段识别", _POWERSHELL)
        self.assertIn("$dateItemMatches.Count -gt 1", _POWERSHELL)

    def test_date_item_matching_accepts_real_date_values_not_one_display_format(self):
        self.assertIn("function ConvertTo-PivotDate", _POWERSHELL)
        self.assertIn("[/-]", _POWERSHELL)
        self.assertIn("$itemDate.Date -eq $endDate.Date", _POWERSHELL)
        self.assertIn("Get-TargetNames $target.DateField", _POWERSHELL)

    def test_embedded_powershell_avoids_curly_quotes_that_break_windows_parser(self):
        self.assertNotIn("“", _POWERSHELL)
        self.assertNotIn("”", _POWERSHELL)


if __name__ == "__main__":
    unittest.main()
