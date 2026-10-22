import json
import tempfile
import unittest
from pathlib import Path

from marketing_calendar.config import ConfigError, PROJECT_ROOT, load_config


class ConfigTests(unittest.TestCase):
    def test_defaults_are_portable_and_direct(self) -> None:
        config = load_config()
        self.assertEqual(config.timezone, "Asia/Shanghai")
        self.assertEqual(config.browser.channel, "msedge")
        self.assertEqual(config.paths.output, PROJECT_ROOT / "output")

    def test_example_config_loads(self) -> None:
        config = load_config(PROJECT_ROOT / "config" / "config.example.json")
        self.assertEqual(config.browser.timeout_ms, 30_000)
        self.assertEqual(
            config.site.report_url,
            "https://one.alimama.com/index.html#/report/campaign",
        )
        self.assertEqual(config.download.timeout_seconds, 600)

    def test_proxy_keys_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "config.json"
            path.write_text(json.dumps({"browser": {"proxy": "forbidden"}}))
            with self.assertRaises(ConfigError):
                load_config(path)

    def test_invalid_timezone_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "config.json"
            path.write_text(json.dumps({"timezone": "UTC"}))
            with self.assertRaises(ConfigError):
                load_config(path)


if __name__ == "__main__":
    unittest.main()

