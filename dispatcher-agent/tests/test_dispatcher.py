from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
if str(BASE) not in sys.path:
    sys.path.insert(0, str(BASE))

from agent import agentrc                        # noqa: E402
from agent.config import Config                  # noqa: E402
from agent.tools import build                    # noqa: E402
from agent.toolkit import Sandbox                # noqa: E402


class DispatcherTools(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        (self.root / "fake").mkdir()

        (self.root / "fake" / "ok.py").write_text(
            'print("采集完成：2 张来源卡")', encoding="utf-8")
        (self.root / "fake" / "reject.py").write_text(
            'print("校验结果：驳回；疑点：RD_CLAIM_002 无原文支撑")', encoding="utf-8")
        (self.root / "fake" / "pass.py").write_text(
            'print("全部通过")', encoding="utf-8")
        (self.root / "fake" / "slow.py").write_text(
            "import time\ntime.sleep(5)\nprint('done')", encoding="utf-8")
        (self.root / "fake" / "crash.py").write_text(
            "import sys\nsys.stderr.write('boom')\nsys.exit(2)", encoding="utf-8")

        self.config = Config(
            base_dir=self.root / "dispatcher-agent",
            COLLECTOR_RUN_CLI="fake/ok.py",
            KNOWLEDGE_RUN_CLI="fake/missing.py",
            GENERATOR_RUN_CLI="fake/ok.py",
            VERIFIER_RUN_CLI="fake/reject.py",
            AGENT_TIMEOUT="8",
        )
        self.registry = build(self.config, Sandbox(self.config.workspace))

    def tearDown(self):
        self.temp.cleanup()

    def _audit_lines(self):
        path = self.config.extra_dirs["audit"] / "audit_log.jsonl"
        if not path.is_file():
            return []
        return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]

    def test_seven_tools(self):
        self.assertEqual(set(self.registry.names()),
                         {"run_collector", "run_knowledge", "run_generator",
                          "run_verifier", "list_agents", "read_file", "list_dir"})

    def test_success_and_audit(self):
        output = self.registry.call("run_collector", '{"task": "搜 CPAP"}')
        self.assertIn("调用成功", output)
        self.assertIn("2 张来源卡", output)
        lines = self._audit_lines()
        self.assertEqual(len(lines), 1)
        self.assertEqual(lines[0]["target"], "采集 Agent")
        self.assertTrue(lines[0]["ok"])

    def test_missing_downstream_is_reported(self):
        output = self.registry.call("run_knowledge", '{"task": "入库"}')
        self.assertIn("入口不存在", output)
        self.assertIn("不能伪造", output)

    def test_nonzero_exit_is_reported(self):
        self.config.settings["COLLECTOR_RUN_CLI"] = "fake/crash.py"
        registry = build(self.config, Sandbox(self.config.workspace))
        output = registry.call("run_collector", '{"task": "x"}')
        self.assertIn("返回码 2", output)
        self.assertIn("boom", output)

    def test_timeout_is_reported(self):
        self.config.settings["COLLECTOR_RUN_CLI"] = "fake/slow.py"
        self.config.timeout = 1
        registry = build(self.config, Sandbox(self.config.workspace))
        output = registry.call("run_collector", '{"task": "x"}')
        self.assertIn("超时", output)

    def test_verifier_verdict_markers(self):
        rejected = self.registry.call("run_verifier", '{"task": "校验"}')
        self.assertIn("verdict=rejected", rejected)

        self.config.settings["VERIFIER_RUN_CLI"] = "fake/pass.py"
        registry = build(self.config, Sandbox(self.config.workspace))
        passed = registry.call("run_verifier", '{"task": "校验"}')
        self.assertIn("verdict=passed", passed)

    def test_list_agents_marks_missing(self):
        output = self.registry.call("list_agents", "{}")
        self.assertIn("知识库", output)
        self.assertIn("缺失", output)

    def test_read_file_guarded(self):
        blocked = self.registry.call("read_file", '{"path": ".env"}')
        self.assertTrue(blocked.startswith("权限拒绝"), blocked)


class RollbackHook(unittest.TestCase):
    class FakeResult(object):
        def __init__(self, rejected):
            self.tool_calls = [{"name": "run_verifier",
                                "result": "verdict=rejected" if rejected else "verdict=passed"}]

    class FakeSession(object):
        def __init__(self):
            self.added = []

        def add_user(self, content):
            self.added.append(content)

    def test_rollback_once(self):
        result = self.FakeResult(rejected=True)
        session = self.FakeSession()
        self.assertTrue(agentrc.after_tools(None, result, session))
        self.assertEqual(len(session.added), 1)
        self.assertIn("回退", session.added[0])
        # 第二次不再回退
        self.assertFalse(agentrc.after_tools(None, result, session))
        self.assertEqual(len(session.added), 1)

    def test_no_rollback_when_passed(self):
        result = self.FakeResult(rejected=False)
        session = self.FakeSession()
        self.assertFalse(agentrc.after_tools(None, result, session))
        self.assertEqual(session.added, [])


if __name__ == "__main__":
    unittest.main()