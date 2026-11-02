import unittest
from pathlib import Path

from marketing_calendar.edge_session import build_edge_command, environment_without_proxy


class EdgeSessionTests(unittest.TestCase):
    def test_proxy_environment_is_removed_case_insensitively(self) -> None:
        cleaned = environment_without_proxy(
            {
                "HTTP_PROXY": "ignored",
                "https_proxy": "ignored",
                "ALL_PROXY": "ignored",
                "NO_PROXY": "ignored",
                "PATH": "kept",
            }
        )
        self.assertEqual(cleaned, {"PATH": "kept"})

    def test_edge_command_uses_dynamic_port_and_direct_network(self) -> None:
        command = build_edge_command(
            Path("msedge.exe"),
            Path("project-profile"),
            54321,
            "https://one.alimama.com/index.html#/report/campaign",
        )
        self.assertIn("--remote-debugging-port=54321", command)
        self.assertIn("--no-proxy-server", command)
        self.assertNotIn("--enable-automation", command)


if __name__ == "__main__":
    unittest.main()

