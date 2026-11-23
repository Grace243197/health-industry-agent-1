# -*- coding: utf-8 -*-
"""
report_pdf.py · Markdown 报告转 PDF（中文友好，纯 Python）

用途：
  把 `output/<run_id>_report.md` 这类报告转成可以直接发给老师/下载的 PDF。

依赖：
  fpdf2（纯 Python，不需要 GTK/浏览器）
  中文字体用系统自带 TTF：Windows 上是 simhei.ttf，macOS/Linux 走常见路径；
  也可以用环境变量 REPORT_FONT 指定一个 .ttf 文件路径。

使用：
  python tools/report_pdf.py output/xxx_report.md
  python tools/report_pdf.py output/xxx_report.md -o output/xxx.pdf

不联网；不调用模型；只做排版。
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path

# 常见中文字体候选。优先 .ttf —— fpdf2 对 .ttc 集合字体的支持依版本而变，
# 直接选单文件 TTF 最稳。
FONT_CANDIDATES = [
    os.environ.get("REPORT_FONT", ""),
    r"C:\Windows\Fonts\simhei.ttf",
    r"C:\Windows\Fonts\msyh.ttc",
    r"C:\Windows\Fonts\simsun.ttc",
    "/System/Library/Fonts/PingFang.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
]


def find_font() -> str:
    """返回一个可用的中文字体路径；找不到就抛清晰的错误。"""
    for path in FONT_CANDIDATES:
        if path and os.path.isfile(path):
            return path
    raise RuntimeError(
        "找不到中文字体。请设置环境变量 REPORT_FONT 指向一个 .ttf 文件，"
        "例如 set REPORT_FONT=C:\\Windows\\Fonts\\simhei.ttf"
    )


# ------------------------------------------------------------ 文本清洗
_MD_LINK = re.compile(r"\[([^\]]*)\]\(([^)]*)\)")
_EMPHASIS = re.compile(r"(\*\*|__|~~|`)")
_EMOJI = re.compile(
    "[\U0001F000-\U0001FAFF\U00002600-\U000027BF\U0001F1E6-\U0001F1FF\uFE0F]"
)


def plain_text(text: str) -> str:
    """去掉 Markdown 标记和字体里没有的字符，避免 PDF 里出现方块或报错。"""
    text = _MD_LINK.sub(lambda m: "{0}（{1}）".format(m.group(1), m.group(2)), text)
    text = _EMPHASIS.sub("", text)
    text = _EMOJI.sub("", text)
    # 只保留 BMP 内字符：非 BMP 字符在多数中文字体里没有字形
    return "".join(ch for ch in text if ord(ch) <= 0xFFFF)


def _clean_cell(text: str) -> str:
    return plain_text(text.replace("<br>", " ")).strip()


# ------------------------------------------------------------ PDF 排版
def _make_pdf(font_path: str):
    from fpdf import FPDF

    class ReportPDF(FPDF):
        def header(self):
            self.set_font("CJK", size=8)
            self.set_text_color(130, 130, 130)
            self.cell(0, 6, "成人睡眠监测 · 调研报告", align="L")
            self.ln(8)
            self.set_text_color(0, 0, 0)

        def footer(self):
            self.set_y(-15)
            self.set_font("CJK", size=8)
            self.set_text_color(130, 130, 130)
            self.cell(0, 8, "第 {0} 页".format(self.page_no()), align="C")
            self.set_text_color(0, 0, 0)

    pdf = ReportPDF(format="A4")
    pdf.add_font("CJK", "", font_path)
    pdf.set_auto_page_break(auto=True, margin=18)
    pdf.set_margins(18, 16, 18)
    pdf.set_font("CJK", size=10.5)
    return pdf


def markdown_to_pdf(markdown_text: str, out_path: Path, title: str = "调研报告") -> Path:
    """把 Markdown 渲染成 PDF。支持的语法：标题、列表、引用、表格、普通段落。

    title 仅用于命令行提示，PDF 页眉固定为项目名，避免和正文标题重复。
    """
    font_path = find_font()
    pdf = _make_pdf(font_path)
    pdf.add_page()
    usable_width = pdf.w - pdf.l_margin - pdf.r_margin

    for raw_line in markdown_text.splitlines():
        line = raw_line.rstrip()
        stripped = line.strip()

        if not stripped:
            pdf.ln(3)
            continue

        # 分隔线
        if re.fullmatch(r"[-*_]{3,}", stripped):
            pdf.ln(1)
            y = pdf.get_y()
            pdf.set_draw_color(210, 210, 210)
            pdf.line(pdf.l_margin, y, pdf.l_margin + usable_width, y)
            pdf.ln(3)
            continue

        # 表格：不画真表格，按行输出并把 | 换成制表符，保证可读、不溢出
        if stripped.startswith("|") and stripped.endswith("|"):
            cells = [c.strip() for c in stripped.strip("|").split("|")]
            if all(re.fullmatch(r":?-{2,}:?", c) for c in cells if c):
                continue                                   # 跳过 |---|---| 分隔行
            pdf.set_font("CJK", size=9)
            pdf.multi_cell(usable_width, 5.6, _clean_cell("  |  ".join(cells)),
                           new_x="LMARGIN", new_y="NEXT", wrapmode="CHAR")
            continue

        # 标题
        heading = re.match(r"^(#{1,4})\s+(.*)$", stripped)
        if heading:
            level, text = len(heading.group(1)), heading.group(2)
            size = {1: 17, 2: 14, 3: 12, 4: 11}.get(level, 11)
            pdf.ln(2 if level > 1 else 0)
            pdf.set_font("CJK", size=size)
            pdf.multi_cell(usable_width, size * 0.62, _clean_cell(text),
                           new_x="LMARGIN", new_y="NEXT")
            pdf.ln(1.5)
            pdf.set_font("CJK", size=10.5)
            continue

        # 引用
        if stripped.startswith(">"):
            pdf.set_font("CJK", size=9.5)
            pdf.set_text_color(90, 90, 90)
            pdf.multi_cell(usable_width, 5.8, _clean_cell(stripped.lstrip("> ")),
                           new_x="LMARGIN", new_y="NEXT", wrapmode="CHAR")
            pdf.set_text_color(0, 0, 0)
            pdf.set_font("CJK", size=10.5)
            continue

        # 列表（含缩进二级）
        bullet = re.match(r"^(\s*)[-*+]\s+(.*)$", line)
        if bullet:
            indent = 4 if len(bullet.group(1)) >= 2 else 0
            pdf.set_x(pdf.l_margin + indent)
            pdf.multi_cell(usable_width - indent, 6.0, "· " + _clean_cell(bullet.group(2)),
                           new_x="LMARGIN", new_y="NEXT", wrapmode="CHAR")
            continue

        numbered = re.match(r"^(\s*)(\d+)[.、)]\s+(.*)$", line)
        if numbered:
            pdf.set_x(pdf.l_margin + (4 if len(numbered.group(1)) >= 2 else 0))
            pdf.multi_cell(usable_width, 6.0,
                           "{0}. {1}".format(numbered.group(2), _clean_cell(numbered.group(3))),
                           new_x="LMARGIN", new_y="NEXT", wrapmode="CHAR")
            continue

        # 普通段落
        pdf.multi_cell(usable_width, 6.2, _clean_cell(stripped),
                       new_x="LMARGIN", new_y="NEXT", wrapmode="CHAR")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    pdf.output(str(out_path))
    return out_path


def main() -> int:
    ap = argparse.ArgumentParser(description="把 Markdown 报告转成 PDF")
    ap.add_argument("markdown", help="输入的 .md 文件")
    ap.add_argument("-o", "--output", default=None, help="输出 .pdf 路径，默认同名同目录")
    ap.add_argument("--title", default=None, help="页眉标题，默认取文件名")
    args = ap.parse_args()

    src = Path(args.markdown)
    if not src.is_file():
        print("找不到文件：{0}".format(src))
        return 2

    out = Path(args.output) if args.output else src.with_suffix(".pdf")
    title = args.title or src.stem
    try:
        path = markdown_to_pdf(src.read_text(encoding="utf-8"), out, title)
    except Exception as exc:                                  # noqa: BLE001
        print("生成失败：{0}: {1}".format(type(exc).__name__, exc))
        return 1

    print("已生成：{0}（{1} 字节）".format(path, path.stat().st_size))
    return 0


if __name__ == "__main__":
    sys.exit(main())