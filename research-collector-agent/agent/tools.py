# -*- coding: utf-8 -*-
"""
tools.py · 采集员的手和脚（本 Agent 专有，手写）

五个工具（与任务书 01 一致）：
  web_search  发现候选线索（free / qwen / both 三后端）
  web_fetch   抓原文（HTML / PDF / 纯文本），并给出最终 URL 与抓取时间
  save_file   在 sources/ 沙箱内写来源卡
  read_file / list_dir

纪律写进工具说明里：搜索只给线索，正文必须 fetch。
"""

from __future__ import annotations

import datetime
import html.parser
import os
import re
import urllib.parse

import requests

from . import search as search_router
from .toolkit import ToolRegistry

MAX_BYTES = 5 * 1024 * 1024
BLOCK_TAGS = {"p", "div", "br", "li", "ul", "ol", "tr", "td", "th", "table",
              "h1", "h2", "h3", "h4", "h5", "h6", "section", "article", "blockquote", "pre"}
SKIP_TAGS = {"script", "style", "noscript", "template", "svg"}


class _TextExtractor(html.parser.HTMLParser):
    """标准库抽正文，不引 bs4。多留导航/页脚也比漏正文安全。"""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts, self.skip = [], 0

    def handle_starttag(self, tag, attrs):
        if tag in SKIP_TAGS:
            self.skip += 1
        elif tag in BLOCK_TAGS:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in SKIP_TAGS:
            self.skip = max(0, self.skip - 1)
        elif tag in BLOCK_TAGS:
            self.parts.append("\n")

    def handle_data(self, data):
        if not self.skip:
            self.parts.append(data)

    def text(self):
        raw = "".join(self.parts)
        lines = [re.sub(r"[ \t\u3000]+", " ", line).strip() for line in raw.splitlines()]
        return "\n".join(line for line in lines if line)


def _assert_public(url):
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise ValueError("只支持 http/https，收到：{0}".format(parsed.scheme or "(空)"))
    host = (parsed.hostname or "").lower()
    if not host:
        raise ValueError("URL 缺少主机名")
    if host in ("localhost", "::1") or host.startswith(
            ("127.", "10.", "192.168.", "169.254.", "0.")):
        raise PermissionError("拒绝访问内网地址：{0}".format(host))


def _decode(raw, content_type):
    match = re.search(r"charset=([\w\-]+)", content_type or "", re.I)
    for encoding in ((match.group(1) if match else "utf-8"), "utf-8", "gb18030"):
        try:
            return raw.decode(encoding)
        except (UnicodeDecodeError, LookupError):
            continue
    return raw.decode("utf-8", errors="replace")


def _to_text(raw, url, content_type):
    if raw.startswith(b"%PDF"):
        try:
            from pypdf import PdfReader
        except ImportError:
            raise RuntimeError("解析 PDF 需要 pypdf：pip install pypdf")
        import io
        reader = PdfReader(io.BytesIO(raw))
        text = "\n\n".join((page.extract_text() or "") for page in reader.pages)
        if not text.strip():
            raise ValueError("PDF 抽不出文字（多半是扫描件），需先 OCR")
        return text, "PDF"

    decoded = _decode(raw, content_type)
    looks_html = ("html" in (content_type or "").lower()
                  or url.lower().split("?")[0].endswith((".html", ".htm", ".shtml"))
                  or decoded.lstrip()[:1] == "<")
    if not looks_html:
        return decoded.strip(), "文本"

    parser = _TextExtractor()
    parser.feed(decoded)
    text = parser.text()
    if not text.strip():
        raise ValueError("页面没有抽出正文")
    return text, "HTML"


def build(config, sandbox):
    registry = ToolRegistry()

    @registry.register
    def web_search(query, top_k=5):
        """检索学术与百科来源，返回候选线索（标题 + URL + 摘要 + 来源接口）。

        注意：这里返回的一切都只是「待核实线索」，其中的数字、结论、摘要
        不能直接写进来源卡。必须再用 web_fetch 抓取原文核实。

        Args:
            query: 中文或英文检索词，尽量具体，例如 "CPAP adherence cardiovascular outcomes"
            top_k: 返回多少条候选，默认 5
        """
        items, errors = search_router.run(
            query, int(top_k), config.search_backend, config.search_timeout,
            api_key=config.api_key, model=config.model)

        lines = ["【线索】以下结果尚未核实，正文必须用 web_fetch 抓取。"]
        if errors:
            lines.append("（部分来源失败：{0}）".format("；".join(errors)))
        if not items:
            lines.append("未检索到结果。可换更具体的关键词，或检查网络。")
            return "\n".join(lines)

        for index, item in enumerate(items, 1):
            lines.append("[{0}] {1}".format(index, item.get("title") or "(无标题)"))
            lines.append("    URL: {0}".format(item.get("url", "")))
            if item.get("snippet"):
                lines.append("    线索: {0}".format(item["snippet"]))
            lines.append("    来源: {0}".format(item.get("api", "未知")))
        return "\n".join(lines)

    @registry.register
    def web_fetch(url, max_chars=6000):
        """抓取网页或 PDF 并返回纯文本原文（含最终 URL 与抓取时间）。

        关键信息必须经过本工具核实后才能写进来源卡。抓取失败会明确返回失败原因，
        不要用摘要或记忆替代原文。

        Args:
            url: http/https 链接
            max_chars: 最多返回多少字符，默认 6000
        """
        _assert_public(url)
        response = requests.get(
            url, timeout=config.search_timeout, stream=True,
            headers={"User-Agent": "sleep-research-agent/3.0 (+student project)"})
        response.raise_for_status()

        chunks, size = [], 0
        for chunk in response.iter_content(8192):
            size += len(chunk)
            if size > MAX_BYTES:
                response.close()
                raise ValueError("文件超过 {0} MB 上限".format(MAX_BYTES // (1024 * 1024)))
            chunks.append(chunk)

        text, kind = _to_text(b"".join(chunks), response.url,
                              response.headers.get("Content-Type", ""))
        limit = max(1, int(max_chars))
        body = text[:limit]
        if len(text) > limit:
            body += "\n...(原文共 {0} 字符，只返回前 {1})".format(len(text), limit)

        return "最终URL: {0}\n抓取时间: {1}\n类型: {2}\n\n{3}".format(
            response.url, datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"), kind, body)

    @registry.register
    def save_file(path, content):
        """把内容写入 sources/ 目录（来源卡存这里）。

        来源卡必须包含：source_id / title / source_type / url_or_path /
        fetched_at / raw_excerpt / is_corporate_material / note。

        Args:
            path: 相对 sources/ 的路径，例如 "SRC001.md"
            content: 完整文件内容
        """
        target = sandbox.resolve(path)
        parent = os.path.dirname(target)
        if parent and not os.path.isdir(parent):
            os.makedirs(parent)
        with open(target, "w", encoding="utf-8") as file:
            file.write(content)
        return "已写入 {0}（{1} 字符）".format(sandbox.display(target), len(content))

    @registry.register
    def read_file(path):
        """读取 sources/ 内某个文件的全文。

        Args:
            path: 相对 sources/ 的路径
        """
        target = sandbox.resolve(path)
        if not os.path.isfile(target):
            raise FileNotFoundError("文件不存在：{0}".format(sandbox.display(target)))
        with open(target, "r", encoding="utf-8", errors="replace") as file:
            return file.read()

    @registry.register
    def list_dir(path="."):
        """列出 sources/ 下某个目录的文件与子目录。

        Args:
            path: 相对 sources/ 的目录，默认 '.'
        """
        target = sandbox.resolve(path)
        if not os.path.isdir(target):
            raise NotADirectoryError("不是目录：{0}".format(sandbox.display(target)))
        rows = []
        for name in sorted(os.listdir(target)):
            full = os.path.join(target, name)
            rows.append("[目录] " + name if os.path.isdir(full)
                        else "[文件] {0} ({1} 字节)".format(name, os.path.getsize(full)))
        return "\n".join(rows) if rows else "(空目录)"

    return registry