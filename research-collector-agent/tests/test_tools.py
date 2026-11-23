from __future__ import annotations

import sys
import unittest
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
if str(BASE) not in sys.path:
    sys.path.insert(0, str(BASE))

from agent import tools as collector_tools      # noqa: E402
from agent.config import Config                 # noqa: E402
from agent.toolkit import Sandbox               # noqa: E402


class CollectorSmoke(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.config = Config()
        cls.sandbox = Sandbox(cls.config.workspace)
        cls.registry = collector_tools.build(cls.config, cls.sandbox)

    def test_five_tools_registered(self):
        self.assertEqual(set(self.registry.names()),
                         {"web_search", "web_fetch", "save_file", "read_file", "list_dir"})

    def test_html_extraction_drops_script(self):
        raw = "<html><body><h1>监测</h1><script>alert(1)</script><p>血氧</p></body></html>"
        text, kind = collector_tools._to_text(raw.encode("utf-8"), "x.html", "text/html")
        self.assertEqual(kind, "HTML")
        self.assertIn("监测", text)
        self.assertIn("血氧", text)
        self.assertNotIn("alert", text)

    def test_intranet_blocked(self):
        for url in ("http://127.0.0.1/a", "http://192.168.1.1/b", "http://localhost/c"):
            with self.assertRaises(PermissionError):
                collector_tools._assert_public(url)

    def test_non_http_scheme_rejected(self):
        with self.assertRaises(ValueError):
            collector_tools._assert_public("file:///C:/Windows/win.ini")

    def test_sandbox_blocks_escape(self):
        with self.assertRaises(PermissionError):
            self.sandbox.resolve("../../.env")


if __name__ == "__main__":
    unittest.main()