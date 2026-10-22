import unittest
from unittest.mock import Mock, patch

from marketing_calendar.browser import (
    EXPECTED_PLAYWRIGHT_VERSION,
    BrowserError,
    detect_login_state,
    validate_playwright_version,
)


class BrowserTests(unittest.TestCase):
    def test_expected_playwright_version_is_locked(self) -> None:
        with patch(
            "marketing_calendar.browser.installed_playwright_version",
            return_value=EXPECTED_PLAYWRIGHT_VERSION,
        ):
            self.assertEqual(validate_playwright_version(), EXPECTED_PLAYWRIGHT_VERSION)

    def test_version_mismatch_fails_before_browser_launch(self) -> None:
        with patch(
            "marketing_calendar.browser.installed_playwright_version",
            return_value="0.0.0",
        ):
            with self.assertRaises(BrowserError):
                validate_playwright_version()

    def test_login_url_is_not_treated_as_authenticated(self) -> None:
        page = Mock()
        page.url = "https://example.invalid/login"
        state = detect_login_state(page)
        self.assertFalse(state.logged_in)

    def test_target_page_without_authenticated_markers_is_not_authenticated(self) -> None:
        page = Mock()
        page.url = "https://one.alimama.com/index.html#/report/campaign"
        page.get_by_text.return_value.count.return_value = 0
        state = detect_login_state(page)
        self.assertFalse(state.logged_in)

    def test_target_page_with_visible_report_marker_is_authenticated(self) -> None:
        page = Mock()
        page.url = "https://one.alimama.com/index.html#/report/campaign"
        marker = Mock()
        marker.count.return_value = 1
        marker.nth.return_value.is_visible.return_value = True
        missing = Mock()
        missing.count.return_value = 0
        page.get_by_text.side_effect = lambda text, exact: (
            marker if text == "基础报表" else missing
        )
        state = detect_login_state(page)
        self.assertTrue(state.logged_in)

    def test_logged_in_home_navigation_is_authenticated(self) -> None:
        page = Mock()
        page.url = "https://one.alimama.com/index.html"
        visible = Mock()
        visible.count.return_value = 1
        visible.nth.return_value.is_visible.return_value = True
        missing = Mock()
        missing.count.return_value = 0
        page.get_by_text.side_effect = lambda text, exact: (
            visible if text in {"首页", "报表"} else missing
        )
        state = detect_login_state(page)
        self.assertTrue(state.logged_in)

    def test_diagnostic_url_removes_query_and_fragment(self) -> None:
        from marketing_calendar.browser import BrowserManager

        sanitized = BrowserManager._sanitize_url(
            "https://example.invalid/path?secret=value#section"
        )
        self.assertEqual(sanitized, "https://example.invalid/path")


if __name__ == "__main__":
    unittest.main()

