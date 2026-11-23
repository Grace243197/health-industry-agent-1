from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
if str(BASE) not in sys.path:
    sys.path.insert(0, str(BASE))

from agent.config import Config                 # noqa: E402
from agent.tools import build, preflight        # noqa: E402
from agent.toolkit import Sandbox               # noqa: E402


class DoubleSourceGate(unittest.TestCase):
    """验收第 3 条：只给一路素材时必须拒绝生成。"""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        (root / "knowledge-agent" / "knowledge_base" / "frozen").mkdir(parents=True)
        (root / "research-collector-agent" / "sources").mkdir(parents=True)
        self.config = Config(base_dir=root / "generator-agent",
                             KB_FROZEN_DIR=str(root / "knowledge-agent/knowledge_base/frozen"),
                             KB_REGISTRY=str(root / "knowledge-agent/knowledge_base/registry.jsonl"),
                             COLLECTOR_SOURCES_DIR=str(root / "research-collector-agent/sources"))

    def tearDown(self):
        self.temp.cleanup()

    def _write(self, relative, text):
        path = self.config.base_dir.parent / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    def test_both_missing(self):
        ok, message = preflight(self.config)
        self.assertFalse(ok)
        self.assertIn("双源强制", message)

    def test_only_baseline_rejected(self):
        self._write("knowledge-agent/knowledge_base/frozen/F001.md", "# 基线\nCPAP 是金标准")
        ok, message = preflight(self.config)
        self.assertFalse(ok)
        self.assertIn("调研来源卡", message)

    def test_only_sources_rejected(self):
        self._write("research-collector-agent/sources/SRC001.md", "- source_id: SRC001")
        ok, message = preflight(self.config)
        self.assertFalse(ok)
        self.assertIn("固化基线", message)

    def test_both_present_ok(self):
        self._write("knowledge-agent/knowledge_base/frozen/F001.md", "# 基线\nCPAP 是金标准")
        self._write("research-collector-agent/sources/SRC001.md", "- source_id: SRC001")
        ok, _ = preflight(self.config)
        self.assertTrue(ok)


class GeneratorTools(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        (root / "knowledge-agent/knowledge_base/frozen").mkdir(parents=True)
        (root / "research-collector-agent/sources").mkdir(parents=True)
        (root / "knowledge-agent/knowledge_base/frozen/F001.md").write_text(
            "# 基线\n\n- source_id: SRC010\n- title: CPAP 基线\n\nCPAP 是成人 OSA 的一线治疗。",
            encoding="utf-8")
        (root / "knowledge-agent/knowledge_base/registry.jsonl").write_text(
            '{"source_id": "SRC010", "evidence_level": "A", "title": "CPAP 基线"}\n',
            encoding="utf-8")
        (root / "research-collector-agent/sources/SRC001.md").write_text(
            "# 某产品手册\n\n- source_id: SRC001\n- title: 澜猫 X8\n"
            "- is_corporate_material: true\n\n声称可增强慢波。",
            encoding="utf-8")

        self.config = Config(base_dir=root / "generator-agent",
                             KB_FROZEN_DIR=str(root / "knowledge-agent/knowledge_base/frozen"),
                             KB_REGISTRY=str(root / "knowledge-agent/knowledge_base/registry.jsonl"),
                             COLLECTOR_SOURCES_DIR=str(root / "research-collector-agent/sources"))
        self.sandbox = Sandbox(self.config.workspace)
        self.registry = build(self.config, self.sandbox)

    def tearDown(self):
        self.temp.cleanup()

    def test_five_tools(self):
        self.assertEqual(set(self.registry.names()),
                         {"search_knowledge", "load_source_cards", "read_file",
                          "list_dir", "save_report"})

    def test_search_knowledge_carries_level(self):
        output = self.registry.call("search_knowledge", '{"query": "CPAP 一线治疗"}')
        self.assertIn("SRC010", output)
        self.assertIn("| A]", output)

    def test_long_sentence_still_hits(self):
        """整句当检索词也要能命中：中文按二元组切分。"""
        output = self.registry.call(
            "search_knowledge", '{"query": "生成成人睡眠监测技术现状报告"}')
        self.assertIn("SRC010", output)

    def test_source_card_flags_corporate_material(self):
        output = self.registry.call("load_source_cards", '{"source_id": "SRC001"}')
        self.assertIn("is_corporate_material: true", output)

    def test_save_report_writes_only_into_reports(self):
        self.assertIn("已写入", self.registry.call(
            "save_report", '{"path": "r.md", "content": "# 报告"}'))
        self.assertTrue((self.config.workspace / "r.md").is_file())
        blocked = self.registry.call(
            "save_report", '{"path": "../escape.md", "content": "x"}')
        self.assertTrue(blocked.startswith("权限拒绝"), blocked)


if __name__ == "__main__":
    unittest.main()