# -*- coding: utf-8 -*-
"""
ask_report.py · 一句话 → 带证据的答案 + Markdown/PDF 报告

用途：
  用户问一个问题，先在本地知识库里检索原文片段，再给出带 [Sxxx] 引用的答案，
  最后落成 `output/<时间戳>_report.md` 和同名 PDF。

设计边界（很重要）：
  - 检索永远走本地 `kb_search`，不联网、不烧 token；
  - 只有配置了 `DASHSCOPE_API_KEY` 才会调模型把片段组织成通顺答案；
    没有密钥时退化为"原文汇总"，并在报告里明确写"未调用模型"，
    绝不假装这是一段模型推理出来的结论；
  - 模型只允许使用传入的证据，提示词里禁止补充证据之外的内容。

使用：
  python tools/ask_report.py "CPAP 依从性对疗效有什么影响"
  python tools/ask_report.py "问题" --top-k 8 --no-llm
"""

from __future__ import annotations

import argparse
import datetime
import json
import os
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

from kb_search import load_registry, search

ROOT = Path(__file__).resolve().parent.parent
OUTPUT = ROOT / "output"

DEFAULT_BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"
DEFAULT_MODEL = "qwen-plus"

# 问句里的高频虚词，拿去检索只会增加噪声
STOPWORDS = {
    "什么", "怎么", "如何", "为什么", "哪些", "哪个", "是否", "可以", "能否",
    "请问", "一下", "我们", "他们", "这个", "那个", "以及", "还有", "目前",
    "现在", "方面", "情况", "问题", "影响", "相关", "进行", "需要", "应该",
    "的", "了", "是", "在", "和", "与", "或", "有", "对", "把", "被", "吗",
}


# ------------------------------------------------------------ 检索
def extract_terms(question: str, max_terms: int = 6) -> list[str]:
    """把问句拆成可检索的词：中文按标点/虚词切，英文按单词切。"""
    chunks = re.split(r"[\s，。！？、；：“”‘’（）()\[\]【】/\\|,.;:!?\"']+", question)
    terms: list[str] = []

    for chunk in chunks:
        chunk = chunk.strip()
        if not chunk:
            continue
        for piece in re.split(r"(?<=[\u4e00-\u9fff])(?=[A-Za-z0-9])|(?<=[A-Za-z0-9])(?=[\u4e00-\u9fff])", chunk):
            piece = piece.strip()
            if not piece or piece in STOPWORDS:
                continue
            if len(piece) >= 2 or re.fullmatch(r"[A-Za-z]{2,}", piece):
                terms.append(piece)

    # 去重保序
    seen, ordered = set(), []
    for term in terms:
        key = term.lower()
        if key not in seen:
            seen.add(key)
            ordered.append(term)
    return ordered[:max_terms]


def collect_evidence(question: str, top_k: int = 6) -> list[dict]:
    """按多个关键词检索并合并去重，返回带来源元信息的证据列表。"""
    levels = {rec.get("source_id"): rec for rec in load_registry()}
    terms = extract_terms(question)
    if not terms:
        terms = [question]

    evidence: list[dict] = []
    seen: set[tuple[str, str]] = set()

    for term in terms:
        for hit in search(term, None, max(1, top_k)):
            for match in hit.get("matches", []):
                fingerprint = (hit["source_id"], match["text"][:60])
                if fingerprint in seen:
                    continue
                seen.add(fingerprint)
                rec = levels.get(hit["source_id"], {})
                evidence.append({
                    "source_id": hit["source_id"],
                    "title": hit.get("title", ""),
                    "evidence_level": rec.get("evidence_level", "C"),
                    "type": rec.get("type", "other"),
                    "file": match["file"],
                    "text": match["text"].strip(),
                    "term": term,
                })
                if len(evidence) >= top_k:
                    return evidence

    return evidence


# ------------------------------------------------------------ 模型（可选）
def _api_key() -> str:
    key = os.environ.get("DASHSCOPE_API_KEY") or os.environ.get("AGENT_API_KEY")
    if key:
        return key.strip()
    for path in (ROOT / ".env", ROOT / "config" / ".env"):
        if not path.is_file():
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line.startswith(("DASHSCOPE_API_KEY=", "AGENT_API_KEY=")):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    return ""


def write_answer(question: str, evidence: list[dict]) -> tuple[str, bool]:
    """用证据组织答案。返回 (答案文本, 是否真的调用了模型)。"""
    key = _api_key()
    if not key or not evidence:
        return _fallback_answer(question, evidence), False

    blocks = []
    for item in evidence:
        blocks.append("[{0}]（等级 {1}｜{2}）\n{3}".format(
            item["source_id"], item["evidence_level"], item["title"], item["text"]))

    prompt = (
        "你是睡眠监测行业调研助手。只能用下面给出的证据回答，"
        "不得补充证据之外的数字、结论或常识。每条结论后必须标注来源编号，例如 [S001]。"
        "证据不足时直接说明缺什么，不要猜测。\n\n"
        "问题：{0}\n\n证据：\n{1}".format(question, "\n\n".join(blocks))
    )
    payload = {
        "model": os.environ.get("AGENT_MODEL", DEFAULT_MODEL),
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.2,
        "max_tokens": 900,
    }
    request = urllib.request.Request(
        (os.environ.get("AGENT_BASE_URL", DEFAULT_BASE_URL).rstrip("/")) + "/chat/completions",
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        method="POST",
        headers={"Authorization": "Bearer " + key, "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=90) as response:
            data = json.loads(response.read().decode("utf-8", errors="replace"))
        content = (data.get("choices") or [{}])[0].get("message", {}).get("content", "")
        if content.strip():
            return content.strip(), True
    except (urllib.error.URLError, urllib.error.HTTPError, ValueError, KeyError) as exc:
        return _fallback_answer(question, evidence) + "\n\n（模型调用失败：{0}，以上为本地汇总）".format(
            type(exc).__name__), False

    return _fallback_answer(question, evidence), False


def _fallback_answer(question: str, evidence: list[dict]) -> str:
    if not evidence:
        return ("本地知识库中没有检索到与「{0}」相关的原文。\n\n"
                "可能原因：知识库为空、关键词未命中、或该主题尚未收集资料。"
                "请先把 PDF/网页放进 `inbox/` 并运行 `tools/ingest.py`，"
                "或换一组更具体的关键词。").format(question)
    lines = ["以下为本地知识库命中的原文片段（未经模型改写）：", ""]
    for item in evidence[:5]:
        lines.append("- [{0}]（{1} 级）{2}".format(
            item["source_id"], item["evidence_level"], item["text"]))
    lines.append("")
    lines.append("> 当前未配置模型密钥，因此只做原文汇总，不生成推理结论。")
    return "\n".join(lines)


# ------------------------------------------------------------ 报告
def build_markdown(question: str, answer: str, evidence: list[dict], used_llm: bool) -> str:
    stamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    lines = [
        "# {0}".format(question),
        "",
        "> 生成时间：{0} ｜ 命中来源：{1} 条 ｜ 生成方式：{2}".format(
            stamp, len(evidence), "模型组织（仅限证据）" if used_llm else "本地汇总（未调用模型）"),
        "",
        "## 一、结论",
        "",
        answer,
        "",
        "## 二、证据清单",
        "",
        "| 序号 | 来源 | 等级 | 原文片段 |",
        "| --- | --- | --- | --- |",
    ]
    for index, item in enumerate(evidence, 1):
        snippet = item["text"].replace("|", "／")
        if len(snippet) > 160:
            snippet = snippet[:160] + "…"
        lines.append("| {0} | {1}（{2}） | {3} | {4} |".format(
            index, item["source_id"], item["title"][:30], item["evidence_level"], snippet))

    if not evidence:
        lines.append("| - | 无命中 | - | - |")

    lines.extend(["", "## 三、逐条溯源", ""])
    for item in evidence:
        lines.extend([
            "### [{0}] {1}".format(item["source_id"], item["title"][:60] or "（无标题）"),
            "",
            "- 证据等级：{0}".format(item["evidence_level"]),
            "- 来源类型：{0}".format(item["type"]),
            "- 原文位置：`{0}`".format(item["file"]),
            "- 命中片段：{0}".format(item["text"]),
            "",
        ])

    lines.extend([
        "## 四、方法与限制",
        "",
        "- 检索方式：本地关键词匹配（`tools/kb_search.py`），不联网。",
        "- 生成方式：{0}".format(
            "模型仅使用上方证据组织语言，逐条标注 [Sxxx]。" if used_llm
            else "未配置模型密钥，仅汇总原文片段，不做推理。"),
        "- 证据等级：A = 政府/标准/同行评审或多源交叉；B = 单一权威来源；"
        "C = 企业宣传或单一未交叉验证来源。C 级片段不能单独支撑最终结论。",
        "- 已知限制：关键词匹配会漏掉同义表述；PDF 自动入库默认 C 级，需人工复核后升级。",
        "",
    ])
    return "\n".join(lines)


def answer_question(question: str, top_k: int = 6, use_llm: bool = True,
                    make_pdf: bool = True) -> dict:
    """端到端：检索 → 组织答案 → 写 md → 转 pdf。返回结果字典。"""
    question = (question or "").strip()
    if not question:
        raise ValueError("问题不能为空")

    evidence = collect_evidence(question, top_k)
    answer, used_llm = write_answer(question, evidence) if use_llm else (
        _fallback_answer(question, evidence), False)
    markdown = build_markdown(question, answer, evidence, used_llm)

    OUTPUT.mkdir(parents=True, exist_ok=True)
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    md_path = OUTPUT / "{0}_report.md".format(stamp)
    md_path.write_text(markdown, encoding="utf-8")

    pdf_path = None
    if make_pdf:
        try:
            from report_pdf import markdown_to_pdf
            pdf_path = markdown_to_pdf(markdown, OUTPUT / "{0}_report.pdf".format(stamp),
                                       title=question[:40])
        except Exception as exc:                              # noqa: BLE001
            pdf_path = None
            markdown += "\n\n> PDF 生成失败：{0}: {1}".format(type(exc).__name__, exc)

    return {
        "question": question,
        "answer": answer,
        "evidence": evidence,
        "markdown": markdown,
        "md_path": str(md_path),
        "pdf_path": str(pdf_path) if pdf_path else "",
        "used_llm": used_llm,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="问一个问题，生成带证据的 Markdown/PDF 报告")
    ap.add_argument("question")
    ap.add_argument("--top-k", type=int, default=6)
    ap.add_argument("--no-llm", action="store_true", help="强制只用本地汇总，不调用模型")
    ap.add_argument("--no-pdf", action="store_true", help="只生成 Markdown")
    args = ap.parse_args()

    try:
        result = answer_question(args.question, args.top_k, not args.no_llm, not args.no_pdf)
    except Exception as exc:                                  # noqa: BLE001
        print("失败：{0}: {1}".format(type(exc).__name__, exc))
        return 1

    print(result["answer"])
    print("\n---")
    print("证据条数：{0}".format(len(result["evidence"])))
    print("Markdown：{0}".format(result["md_path"]))
    print("PDF：{0}".format(result["pdf_path"] or "（未生成）"))
    return 0


if __name__ == "__main__":
    sys.exit(main())