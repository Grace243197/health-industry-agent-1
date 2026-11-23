from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
if str(BASE) not in sys.path:
    sys.path.insert(0, str(BASE))

from agent.toolkit import Sandbox, ToolRegistry, build_schema   # noqa: E402


class ToolkitSmoke(unittest.TestCase):
    def test_schema_and_call(self):
        registry = ToolRegistry()

        @registry.register
        def ping(text: str = "x"):
            """回显。

            Args:
                text: 要回显的内容
            """
            return "pong:" + text

        schema = registry.schemas()[0]["function"]
        self.assertEqual(schema["name"], "ping")
        self.assertEqual(registry.call("ping", '{"text": "a"}'), "pong:a")
        self.assertIn("错误", registry.call("ping", "{bad json"))

    def test_sandbox_blocks_escape(self):
        with tempfile.TemporaryDirectory() as temp:
            sandbox = Sandbox(Path(temp) / "ws")
            self.assertTrue(sandbox.resolve("a.txt").startswith(sandbox.root))
            with self.assertRaises(PermissionError):
                sandbox.resolve("../../.env")


if __name__ == "__main__":
    unittest.main()