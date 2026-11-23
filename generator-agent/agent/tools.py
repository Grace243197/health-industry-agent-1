# -*- coding: utf-8 -*-
"""
tools.py · 报告生成员的工具（本 Agent 专有，手写）

五个工具（与任务书 05 一致）：
  search_knowledge   查固化基线（只读），带回 source_id 与证据等级
  load_source_cards  读采集 Agent 的来源卡（只读）
  read_file / list_dir
  save_report        只写 reports/

双源强制不靠模型自觉，靠 preflight() 在执行任务前硬检查。
"""

from __future__ import annotations

import json
import os
import re

from .toolkit import ToolRegistry


# ------------------------------------------------------------ 双源检查
def _md_files(root):
    if not root.is_dir():
        return []
    return sorted(path for path in root.rglob("*.md") if path.is_file())


def preflight(config):
    """生成前必须两路都有素材。返回 (ok, 说明)。缺一路就拒绝生成。"""
    frozen = config.project_path("KB_FROZEN_DIR", "knowledge-agent/knowledge_base/frozen")
    sources = config.project_path("COLLECTOR_SOURCES_DIR", "research-collector-agent/sources")

    frozen_files = _md_files(frozen)
    source_files = _md_files(sources)

    missing = []
    if not frozen_files:
        missing.append("固化基线（{0}）里没有 .md 文件".format(frozen))
    if not source_files:
        missing.append("调研来源卡（{0}）里没有 .md 文件".format(sources))

    if missing:
        return False, ("【双源强制】拒绝生成：\n- " + "\n- ".join(missing) +
                       "\n\n请先补齐两路素材（固化基线来自知识库 Agent，来源卡来自采集 Agent）。")
    return True, "双源就绪：基线 {0} 份，来源卡 {1} 份。".format(
        len(frozen_files), len(source_files))


# ------------------------------------------------------------ 解析
def _load_registry(path):
    levels = {}
    if not path.is_file():
        return levels
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        if record.get("source_id"):
            levels[record["source_id"]] = record
    return levels


def _terms(query):
    """中文按二元组切分。

    为什么不能整句当一个词：模型很可能把"生成成人睡眠监测技术现状报告"整句丢进来，
    如果按整句匹配，除非原文一字不差，否则永远检不到。二元组能让"睡眠/监测/技术"
    分别命中。
    """
    terms = set()
    for run in re.findall(r"[\u4e00-\u9fff]{2,}", query or ""):
        if len(run) <= 6:
            terms.add(run)
        else:
            for index in range(len(run) - 1):
                terms.add(run[index:index + 2])
    for word in re.findall(r"[A-Za-z]{2,}", query or ""):
        terms.add(word.lower())
    return sorted(terms)


def _parse_card(text):
    """从来源卡里抠出关键字段（容错：字段可能写成 - key: value 或 | key | value |）。"""
    fields = {}
    for key in ("source_id", "title", "source_type", "url_or_path",
                "fetched_at", "is_corporate_material", "note"):
        match = re.search(r"^\s*[-|*]*\s*" + key + r"\s*[:：|]\s*(.+?)\s*\|?\s*$",
                          text, re.MULTILINE | re.IGNORECASE)
        if match:
            fields[key] = match.group(1).strip().strip("|").strip()
    if "source_id" not in fields:
        match = re.search(r"(SRC\d{3})", text)
        if match:
            fields["source_id"] = match.group(1)
    return fields


def build(config, sandbox):
    registry = ToolRegistry()

    frozen_dir = config.project_path("KB_FROZEN_DIR", "knowledge-agent/knowledge_base/frozen")
    registry_file = config.project_path(
        "KB_REGISTRY", "knowledge-agent/knowledge_base/registry.jsonl")
    sources_dir = config.project_path(
        "COLLECTOR_SOURCES_DIR", "research-collector-agent/sources")

    @registry.register
    def search_knowledge(query, top_k=5):
        """在固化基线（frozen）里检索，返回片段 + source_id + 证据等级。

        只读固化基线，不得修改。每条结论都必须能对应到这里的某一条命中。

        Args:
            query: 检索词，尽量具体，例如 "CPAP 依从性 心血管"
            top_k: 返回几条，默认 5
        """
        terms = _terms(query)
        if not terms:
            raise ValueError("检索词为空")
        levels = _load_registry(registry_file)
        files = _md_files(frozen_dir)
        if not files:
            return "固化基线为空：{0} 下没有 .md 文件。".format(frozen_dir)

        scored = []
        for path in files:
            text = path.read_text(encoding="utf-8", errors="replace")
            lowered = text.lower()
            score = sum(lowered.count(term) for term in terms)
            if score <= 0:
                continue
            card = _parse_card(text)
            sid = card.get("source_id") or path.stem
            record = levels.get(sid, {})
            line = ""
            for candidate in text.splitlines():
                candidate = candidate.strip()
                if (candidate and not candidate.startswith(("#", "|", "-", "*", ">"))
                        and len(candidate) >= 12):
                    line = candidate
                    break
            scored.append((score, sid, record.get("evidence_level", "C"),
                           record.get("title") or card.get("title") or path.name,
                           line[:220], path.name))

        if not scored:
            return "固化基线里没有命中「{0}」。".format(query)

        scored.sort(reverse=True)
        lines = ["【固化基线命中 {0} 条】（可信、只读）".format(min(top_k, len(scored)))]
        for score, sid, level, title, snippet, name in scored[:int(top_k)]:
            lines.append("- [{0} | {1}] {2}\n    {3}\n    文件：{4}（命中 {5} 次）".format(
                sid, level, title, snippet, name, score))
        return "\n".join(lines)

    @registry.register
    def load_source_cards(source_id=None):
        """读取采集 Agent 产出的来源卡；不传 source_id 时列出全部。

        来源卡是「待核实线索」，企业宣传材料只能写成「XX 声称」。

        Args:
            source_id: 只读某一张，例如 "SRC001"；不填则列出全部卡片摘要
        """
        files = _md_files(sources_dir)
        if not files:
            return "来源卡目录为空：{0}".format(sources_dir)

        cards = []
        for path in files:
            text = path.read_text(encoding="utf-8", errors="replace")
            card = _parse_card(text)
            card.setdefault("source_id", path.stem)
            card["_path"] = path.name
            card["_text"] = text
            cards.append(card)

        if source_id:
            picked = [c for c in cards if c.get("source_id") == source_id]
            if not picked:
                return "没有找到 source_id={0} 的来源卡。".format(source_id)
            card = picked[0]
            return "\n".join([
                "来源卡 {0}（文件 {1}）".format(card.get("source_id"), card["_path"]),
                "- title: {0}".format(card.get("title", "")),
                "- source_type: {0}".format(card.get("source_type", "")),
                "- url_or_path: {0}".format(card.get("url_or_path", "")),
                "- is_corporate_material: {0}".format(card.get("is_corporate_material", "")),
                "- note: {0}".format(card.get("note", "")),
                "",
                card["_text"][:2500],
            ])

        lines = ["【来源卡 {0} 张】（待核实线索）".format(len(cards))]
        for card in cards[:20]:
            lines.append("- [{0}] {1}（企业材料: {2}）".format(
                card.get("source_id"), card.get("title", "")[:60],
                card.get("is_corporate_material", "未知")))
        return "\n".join(lines)

    @registry.register
    def read_file(path):
        """读取 reports/ 内某个文件的全文（例如上一版报告）。

        Args:
            path: 相对 reports/ 的路径
        """
        target = sandbox.resolve(path)
        if not os.path.isfile(target):
            raise FileNotFoundError("文件不存在：{0}".format(path))
        with open(target, "r", encoding="utf-8", errors="replace") as file:
            return file.read()

    @registry.register
    def list_dir(path="."):
        """列出 reports/ 下的文件。

        Args:
            path: 相对 reports/ 的目录，默认 '.'
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

    @registry.register
    def save_report(path, content):
        """把报告写进 reports/（只允许写这个目录）。

        报告必须包含正文与末尾的「证据索引表」：
        claim → source_id → evidence_level → 原文位置。

        Args:
            path: 相对 reports/ 的路径，例如 "report_20261123.md"
            content: 完整报告内容
        """
        target = sandbox.resolve(path)
        parent = os.path.dirname(target)
        if parent and not os.path.isdir(parent):
            os.makedirs(parent)
        with open(target, "w", encoding="utf-8") as file:
            file.write(content)
        return "已写入 reports/{0}（{1} 字符）".format(sandbox.display(target), len(content))

    return registry