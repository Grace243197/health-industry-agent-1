from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
if str(BASE) not in sys.path:
    sys.path.insert(0, str(BASE))

from agent.config import Config                     # noqa: E402
from agent.knowledge import KnowledgeBase, guess_level   # noqa: E402
from agent.toolkit import Sandbox                   # noqa: E402
from agent.tools import build                       # noqa: E402

CARD = """# 澜猫睡眠X8产品手册

- source_id: SRC001
- title: 澜猫睡眠X8产品手册
- source_type: 产品手册
- url_or_path: https://example.com/manual
- is_corporate_material: true

## 原文
本品声称可增强慢波睡眠。
"""

PAPER = """# A wearable EEG device

- source_id: SRC007
- title: LANMAO Sleep Recorder validation
- source_type: paper
- url_or_path: https://pubmed.ncbi.nlm.nih.gov/12345/

## 原文
Sleep of 7 Chinese adults were recorded with PSG.
"""

# W2 时期的卡片是表格体，编号与标题不在 `- key:` 行里
W2_CARD = """# 来源卡 - SRC005

## 基本信息

| 字段 | 内容 |
|------|------|
| **来源编号** | SRC005 |
| **标题** | 华为运动健康技术分享 |
| **来源类型** | 会议纪要 |
| **文件路径** | `knowledge/raw/huawei.pdf` |
"""


class KnowledgeBaseTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        sources = self.root / "research-collector-agent" / "sources"
        sources.mkdir(parents=True)
        (sources / "SRC001.md").write_text(CARD, encoding="utf-8")
        (sources / "SRC007.md").write_text(PAPER, encoding="utf-8")
        (sources / "SRC002.md").write_text(CARD.replace("SRC001", "SRC002").replace(
            "澜猫睡眠X8产品手册", "另一份睡眠宣传页"), encoding="utf-8")
        (sources / "SRC005.md").write_text(W2_CARD, encoding="utf-8")

        self.config = Config(
            base_dir=self.root / "knowledge-agent",
            COLLECTOR_SOURCES_DIR="research-collector-agent/sources",
            KB_DIR="knowledge_base",
        )
        self.kb = KnowledgeBase(self.config.workspace, self.config.project_root,
                                self.config.project_path("COLLECTOR_SOURCES_DIR"))
        self.sandbox = Sandbox(self.config.workspace)
        self.registry = build(self.config, self.sandbox)

    def tearDown(self):
        self.temp.cleanup()

    # ---------------------------------------------------- 预处理
    def test_preprocess_corporate_is_c(self):
        outcome = self.kb.preprocess("research-collector-agent/sources/SRC001.md")
        record = outcome["record"]
        self.assertEqual(record["evidence_level"], "C")
        self.assertEqual(record["status"], "staging")
        self.assertEqual(record["version"], 1)
        self.assertTrue((self.kb.staging_dir / "SRC001.md").is_file())

    def test_preprocess_pubmed_is_a(self):
        outcome = self.kb.preprocess("research-collector-agent/sources/SRC007.md")
        self.assertEqual(outcome["record"]["evidence_level"], "A")

    def test_preprocess_table_card_keeps_id_and_title(self):
        """W2 表格体卡片：编号与标题必须从表格里读出来，不能退化成文件名。"""
        outcome = self.kb.preprocess("research-collector-agent/sources/SRC005.md")
        record = outcome["record"]
        self.assertEqual(record["source_id"], "SRC005")
        self.assertEqual(record["title"], "华为运动健康技术分享")
        self.assertTrue((self.kb.staging_dir / "SRC005.md").is_file())

    def test_preprocess_keeps_original_text(self):
        self.kb.preprocess("research-collector-agent/sources/SRC001.md")
        text = (self.kb.staging_dir / "SRC001.md").read_text(encoding="utf-8")
        self.assertIn("本品声称可增强慢波睡眠。", text)     # 原文逐字保留

    def test_preprocess_rejects_outside_path(self):
        with self.assertRaises(PermissionError):
            self.kb.preprocess("../../.env")

    def test_duplicate_preprocess_rejected(self):
        self.kb.preprocess("research-collector-agent/sources/SRC001.md")
        with self.assertRaises(ValueError):
            self.kb.preprocess("research-collector-agent/sources/SRC001.md")

    # ---------------------------------------------------- 人工闸门
    def test_freeze_without_approver_rejected(self):
        self.kb.preprocess("research-collector-agent/sources/SRC001.md")
        for bad in ("", "   ", "待定", "TODO", "未知"):
            with self.assertRaises(PermissionError, msg=bad):
                self.kb.freeze("SRC001", bad)

    def test_freeze_with_approver_succeeds(self):
        self.kb.preprocess("research-collector-agent/sources/SRC001.md")
        outcome = self.kb.freeze("SRC001", "张三")
        record = outcome["record"]
        self.assertEqual(record["status"], "frozen")
        self.assertEqual(record["approved_by"], "张三")
        self.assertEqual(record["version"], 2)
        self.assertTrue(record["approved_at"])
        self.assertTrue((self.kb.frozen_dir / "SRC001.md").is_file())
        self.assertFalse((self.kb.staging_dir / "SRC001.md").exists())

        saved = [json.loads(line) for line in
                 self.kb.registry_path.read_text(encoding="utf-8").splitlines() if line]
        self.assertEqual(saved[0]["approved_by"], "张三")

    def test_double_freeze_rejected(self):
        self.kb.preprocess("research-collector-agent/sources/SRC001.md")
        self.kb.freeze("SRC001", "张三")
        with self.assertRaises(PermissionError):
            self.kb.freeze("SRC001", "李四")

    def test_freeze_unknown_id(self):
        with self.assertRaises(ValueError):
            self.kb.freeze("SRC999", "张三")

    # ---------------------------------------------------- 归档与检索
    def test_archive_moves_file(self):
        self.kb.preprocess("research-collector-agent/sources/SRC001.md")
        outcome = self.kb.archive("SRC001")
        self.assertEqual(outcome["record"]["status"], "archived")
        self.assertEqual(outcome["record"]["version"], 2)
        self.assertTrue((self.kb.archive_dir / "SRC001.md").is_file())

    def test_search_prefers_frozen(self):
        """同一个关键词在两个库里都命中时，frozen 必须排在 staging 前面。"""
        self.kb.preprocess("research-collector-agent/sources/SRC001.md")
        self.kb.preprocess("research-collector-agent/sources/SRC002.md")
        self.kb.freeze("SRC001", "张三")
        hits = self.kb.search("睡眠", 5)
        statuses = [item["status"] for item in hits]
        self.assertIn("frozen", statuses)
        self.assertIn("staging", statuses)
        self.assertEqual(hits[0]["status"], "frozen")

    def test_search_carries_level(self):
        self.kb.preprocess("research-collector-agent/sources/SRC007.md")
        hits = self.kb.search("PSG")
        self.assertEqual(hits[0]["source_id"], "SRC007")
        self.assertEqual(hits[0]["evidence_level"], "A")

    # ---------------------------------------------------- 工具层
    def test_eight_tools(self):
        self.assertEqual(set(self.registry.names()),
                         {"preprocess_doc", "search_knowledge", "freeze_source",
                          "list_sources", "archive_source",
                          "save_file", "read_file", "list_dir"})

    def test_tool_freeze_message(self):
        self.registry.call("preprocess_doc",
                           '{"path": "research-collector-agent/sources/SRC001.md"}')
        blocked = self.registry.call("freeze_source",
                                     '{"source_id": "SRC001", "approved_by": ""}')
        self.assertTrue(blocked.startswith("权限拒绝"), blocked)
        ok = self.registry.call("freeze_source",
                                '{"source_id": "SRC001", "approved_by": "张三"}')
        self.assertIn("已冻结", ok)

    def test_save_file_cannot_touch_frozen(self):
        blocked = self.registry.call(
            "save_file", '{"path": "frozen/SRC001.md", "content": "x"}')
        self.assertTrue(blocked.startswith("权限拒绝"), blocked)

    def test_list_sources_filter(self):
        self.registry.call("preprocess_doc",
                           '{"path": "research-collector-agent/sources/SRC001.md"}')
        output = self.registry.call("list_sources", '{"status": "staging"}')
        self.assertIn("SRC001", output)


class LevelHeuristics(unittest.TestCase):
    def test_corporate_always_c(self):
        for kwargs in (
            {"title": "产品手册", "source_type": "doc", "url_or_path": "https://x.com/a"},
            {"title": "新闻发布", "source_type": "web", "url_or_path": "https://x.com/b"},
            {"title": "某研究", "source_type": "doc", "url_or_path": "https://x.com/c",
             "is_corporate_material": True},
        ):
            self.assertEqual(guess_level(**kwargs)[0], "C")

    def test_peer_reviewed_is_a(self):
        self.assertEqual(guess_level(
            "PSG validation", "paper", "https://pubmed.ncbi.nlm.nih.gov/1/")[0], "A")

    def test_unknown_is_c(self):
        self.assertEqual(guess_level("随便一篇", "doc", "https://blog.example.com/x")[0], "C")


if __name__ == "__main__":
    unittest.main()