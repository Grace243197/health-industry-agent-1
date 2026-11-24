# -*- coding: utf-8 -*-
"""
tools.py · 知识库管家的工具（本 Agent 专有，手写）

把 knowledge.py 的函数包装成模型能调用的工具，外加沙箱读写。
硬约束：save_file 只能写 staging/，碰 frozen/ 直接拒绝（基线只读）。
"""

from __future__ import annotations

import os

from .knowledge import KnowledgeBase
from .toolkit import ToolRegistry

WRITE_PREFIXES = ("staging",)


def build(config, sandbox):
    kb = KnowledgeBase(
        kb_dir=config.workspace,
        project_root=config.project_root,
        collector_sources=config.project_path(
            "COLLECTOR_SOURCES_DIR", "research-collector-agent/sources"),
    )
    registry = ToolRegistry()

    @registry.register
    def preprocess_doc(path, source_type=""):
        """把一份素材标准化后登记进 staging（临时素材库），并在 registry 记一条账。

        只补元数据、逐字保留原文，不改写内容。新条目一律是 staging，
        不能直接进 frozen —— 冻结必须经过人工批准。

        Args:
            path: 相对项目根的路径，例如 "research-collector-agent/sources/SRC001.md"
            source_type: 可选，web / pdf / doc；不填按文件类型推断
        """
        outcome = kb.preprocess(path, source_type)
        record = outcome["record"]
        return ("已入库：{0}「{1}」\n- 证据等级：{2}（{3}）\n- 状态：staging\n"
                "- 文件：{4}\n- 下一步：需要人工批准才能冻结").format(
            record["source_id"], record["title"], record["evidence_level"],
            record["level_reason"], outcome["path"])

    @registry.register
    def search_knowledge(query, top_k=5):
        """检索知识库（frozen 优先，staging 其次），返回片段 + 来源 + 证据等级。

        Args:
            query: 检索词，例如 "CPAP 依从性"
            top_k: 返回几条，默认 5
        """
        hits = kb.search(query, top_k)
        if not hits:
            return "没有命中「{0}」。".format(query)
        lines = ["命中 {0} 条（frozen 优先）：".format(len(hits))]
        for item in hits:
            lines.append("- [{0} | {1} | {2}] {3}\n    {4}".format(
                item["source_id"], item["evidence_level"], item["status"],
                item["title"], item["snippet"]))
        return "\n".join(lines)

    @registry.register
    def freeze_source(source_id, approved_by=""):
        """把 staging 条目冻结进 frozen（可信基线）。**必须提供人工批准人**。

        没有 approved_by 或写成"待定/TODO"会被拒绝。已经是 frozen/archived 的
        条目再冻结也会被拒绝。冻结后文件只读。

        Args:
            source_id: 例如 "SRC001"
            approved_by: 批准人姓名，必须由人工提供，例如 "张三"
        """
        outcome = kb.freeze(source_id, approved_by)
        record = outcome["record"]
        return ("已冻结：{0}「{1}」\n- status：{2}\n- approved_by：{3}\n- 版本：v{4}\n"
                "- 文件：{5}").format(
            record["source_id"], record["title"], record["status"],
            record["approved_by"], record["version"], outcome["path"])

    @registry.register
    def list_sources(status=None):
        """列出 registry 里的来源；可按 staging / frozen / archived 过滤。

        Args:
            status: 可选，staging / frozen / archived；不填列全部
        """
        records = kb.list_sources(status)
        if not records:
            return "没有符合条件的来源。"
        lines = ["共 {0} 条{1}：".format(len(records), "（{0}）".format(status) if status else "")]
        for record in records:
            lines.append("- [{0}] {1} | {2} | v{3} | {4}".format(
                record.get("source_id"), record.get("status"),
                record.get("evidence_level"), record.get("version", 1),
                record.get("title", "")[:50]))
        return "\n".join(lines)

    @registry.register
    def archive_source(source_id):
        """把条目归档（过时/被替换/废弃）。文件移到 archive/，状态记 archived。

        Args:
            source_id: 例如 "SRC001"
        """
        outcome = kb.archive(source_id)
        record = outcome["record"]
        return "已归档：{0} → {1}（版本 v{2}）".format(
            record["source_id"], record["status"], record["version"])

    def _require_staging(relative):
        normalized = os.path.normpath(relative).replace(os.sep, "/")
        if not any(normalized == p or normalized.startswith(p + "/") for p in WRITE_PREFIXES):
            raise PermissionError(
                "只能写 staging/（frozen 是只读基线），收到：{0}".format(relative))
        return normalized

    @registry.register
    def save_file(path, content):
        """在 staging/ 内写文件（例如预处理备注）。不允许写 frozen/。

        Args:
            path: 相对 knowledge_base/ 的路径，必须以 staging/ 开头
            content: 文件内容
        """
        normalized = _require_staging(path)
        target = sandbox.resolve(normalized)
        parent = os.path.dirname(target)
        if parent and not os.path.isdir(parent):
            os.makedirs(parent)
        with open(target, "w", encoding="utf-8") as file:
            file.write(content)
        return "已写入 {0}（{1} 字符）".format(normalized, len(content))

    @registry.register
    def read_file(path):
        """读取 knowledge_base/ 内某个文件（可读 staging/frozen/archive）。

        Args:
            path: 相对 knowledge_base/ 的路径，例如 "frozen/SRC001.md"
        """
        target = sandbox.resolve(path)
        if not os.path.isfile(target):
            raise FileNotFoundError("文件不存在：{0}".format(path))
        return target.read_text(encoding="utf-8", errors="replace")

    @registry.register
    def list_dir(path="."):
        """列出 knowledge_base/ 下某个目录的内容。

        Args:
            path: 相对 knowledge_base/ 的目录，默认 '.'
        """
        target = sandbox.resolve(path)
        if not os.path.isdir(target):
            raise NotADirectoryError("不是目录：{0}".format(path))
        rows = []
        for name in sorted(os.listdir(target)):
            full = os.path.join(target, name)
            rows.append("[目录] " + name if os.path.isdir(full)
                        else "[文件] {0} ({1} 字节)".format(name, os.path.getsize(full)))
        return "\n".join(rows) if rows else "(空目录)"

    return registry