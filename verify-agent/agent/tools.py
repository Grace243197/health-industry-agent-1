# -*- coding: utf-8 -*-
"""
tools.py · 校验官的四个工具（本 Agent 专有，手写）

grep_source  在 sources/ 原文里做正则检索 —— 这是"逐字比对"的物理基础，
             不靠模型记忆，靠文件里真实存在的字。
read_file    读原文
list_dir     列目录
save_file    写校验报告（只允许写进 verifications/）

读写权限是分开的：能读 sources/ 与 claims/，只能写 verifications/。
"""

from __future__ import annotations

import os
import re

from .toolkit import ToolRegistry

READ_PREFIXES = ("sources", "claims")
WRITE_PREFIXES = ("verifications",)


def _relative(sandbox, path):
    return sandbox.display(sandbox.resolve(path))


def _require_prefix(sandbox, path, prefixes):
    relative = _relative(sandbox, path)
    if not any(relative == p or relative.startswith(p + "/") for p in prefixes):
        raise PermissionError("只允许访问 {0}，收到：{1}".format("/".join(prefixes), relative))
    return sandbox.resolve(path)


def build(config, sandbox):
    registry = ToolRegistry()

    @registry.register
    def grep_source(pattern, source_id=None, max_hits=5):
        """在 sources/ 的原文里做正则检索，返回命中行与上下文。

        校验任何 Claim 之前必须先用本工具在原文里找对应文字。
        找不到就是找不到 —— 不允许用模型自己的知识补位。

        Args:
            pattern: 正则或关键词，例如 "polysomnography|PSG"、"500Hz"
            source_id: 只搜某个来源（文件名包含该编号），例如 "SRC001"；不填则搜全部
            max_hits: 最多返回多少条命中，默认 5
        """
        try:
            compiled = re.compile(pattern, re.IGNORECASE)
        except re.error as exc:
            raise ValueError("正则不合法：{0}".format(exc))

        root = sandbox.root
        targets = []
        for dirpath, _, filenames in os.walk(os.path.join(root, "sources")):
            for name in sorted(filenames):
                if not name.lower().endswith((".md", ".txt")):
                    continue
                if source_id and source_id.lower() not in name.lower():
                    continue
                targets.append(os.path.join(dirpath, name))

        if not targets:
            return "sources/ 下没有可检索的原文（先放入来源卡或抽好的文本）。"

        hits, scanned = [], 0
        for path in targets:
            scanned += 1
            with open(path, "r", encoding="utf-8", errors="replace") as file:
                lines = file.read().splitlines()
            for line_no, line in enumerate(lines, 1):
                if not compiled.search(line):
                    continue
                hits.append("【{0} 第 {1} 行】{2}".format(
                    os.path.basename(path), line_no, line.strip()[:300]))
                if len(hits) >= int(max_hits):
                    break
            if len(hits) >= int(max_hits):
                break

        if not hits:
            return "未命中：{0} 个文件里都没有匹配「{1}」的原文。".format(scanned, pattern)
        return "命中 {0} 条（扫描 {1} 个文件）：\n\n{2}".format(len(hits), scanned, "\n".join(hits))

    @registry.register
    def read_file(path):
        """读取 sources/ 或 claims/ 下的文件全文。

        Args:
            path: 相对本目录的路径，例如 "sources/SRC001.md" 或 "claims/RD_CLAIM_001.md"
        """
        target = _require_prefix(sandbox, path, READ_PREFIXES)
        if not os.path.isfile(target):
            raise FileNotFoundError("文件不存在：{0}".format(path))
        with open(target, "r", encoding="utf-8", errors="replace") as file:
            return file.read()

    @registry.register
    def list_dir(path="."):
        """列出某个目录下的文件（可看 sources/、claims/、verifications/）。

        Args:
            path: 相对本目录的路径，默认 '.'
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
    def save_file(path, content):
        """把校验报告写入 verifications/（只允许写这个目录）。

        报告字段：claim_id / claim_text / verdict / source_id / 原文引用 / reason /
        hallucination_type。verdict 只能是 verified、partially_supported、
        contradicted、insufficient 四者之一。

        Args:
            path: 相对 verifications/ 的路径，例如 "VER-CLM001.md"
            content: 完整报告内容
        """
        target = _require_prefix(sandbox, path, WRITE_PREFIXES)
        parent = os.path.dirname(target)
        if parent and not os.path.isdir(parent):
            os.makedirs(parent)
        with open(target, "w", encoding="utf-8") as file:
            file.write(content)
        return "已写入 {0}（{1} 字符）".format(_relative(sandbox, path), len(content))

    return registry