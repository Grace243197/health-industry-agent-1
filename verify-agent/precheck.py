# -*- coding: utf-8 -*-
"""
precheck.py · 规则版预检（不调用模型）

作用：在没有模型密钥、或想先筛一遍时，用**确定性规则**给出一个初步判断：
      Claim 里的关键数字在不在原文里、关键措辞的重合度有多高。

它**不是**最终 verdict，只是给校验官（模型）和人工一个排序依据。
报告里会明确标注"规则预检"，避免被当成模型判定。

使用：
  python run_cli.py --precheck
  python run_cli.py --precheck --claims claims --sources sources
"""

from __future__ import annotations

import datetime
import json
import re
from pathlib import Path


def _tokens(text: str) -> set:
    tokens = set()
    for run in re.findall(r"[\u4e00-\u9fff]{2,}", text or ""):
        if len(run) <= 6:
            tokens.add(run)
        for index in range(len(run) - 1):
            tokens.add(run[index:index + 2])
    for word in re.findall(r"[A-Za-z]{3,}", text or ""):
        tokens.add(word.lower())
    return tokens


def load_claims(claims_dir: Path) -> list:
    """支持两种格式：claims/*.json（数组）与 claims/*.md（带 claim_id/source_id 行）。"""
    claims = []
    for path in sorted(claims_dir.glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        for item in (data if isinstance(data, list) else [data]):
            statement = item.get("statement") or item.get("claim_text") or ""
            if not statement:
                continue
            ids = item.get("source_id") or item.get("source_ids") or []
            claims.append({
                "claim_id": item.get("claim_id") or path.stem,
                "statement": statement,
                "source_ids": [ids] if isinstance(ids, str) else list(ids),
                "expected": item.get("状态") or item.get("verdict") or "",
                "file": path.name,
            })

    for path in sorted(claims_dir.glob("*.md")):
        text = path.read_text(encoding="utf-8", errors="replace")
        ids = re.findall(r"SRC\d{3}", text)
        match = re.search(r"(?:claim_text|statement)\s*[:：]\s*(.+)", text)
        claims.append({
            "claim_id": path.stem,
            "statement": match.group(1).strip() if match else text.strip()[:400],
            "source_ids": sorted(set(ids)),
            "expected": "",
            "file": path.name,
        })
    return claims


def _source_text(sources_dir: Path, source_ids) -> str:
    chunks = []
    for path in sorted(sources_dir.rglob("*")):
        if not path.is_file():
            continue
        if source_ids and not any(sid in path.name for sid in source_ids):
            continue
        try:
            chunks.append(path.read_text(encoding="utf-8", errors="replace"))
        except OSError:
            continue
    return "\n".join(chunks)


def check_one(claim: dict, sources_dir: Path) -> dict:
    statement = claim["statement"]
    source_text = _source_text(sources_dir, claim["source_ids"])
    lowered = source_text.lower()

    if not source_text.strip():
        return {"verdict": "insufficient", "reason": "找不到对应原文",
                "coverage": 0.0, "missing_numbers": []}

    # 先去掉 SRC001 这类编号，免得把来源编号当成"数字证据"
    cleaned = re.sub(r"SRC\d+", " ", statement)
    numbers = [n for n in re.findall(r"\d+(?:\.\d+)?", cleaned)]
    missing_numbers = [n for n in numbers if n not in source_text]

    tokens = _tokens(cleaned)
    found = {token for token in tokens if token in lowered}
    coverage = len(found) / len(tokens) if tokens else 0.0

    if missing_numbers and coverage >= 0.5:
        verdict, reason = "contradicted", "关键数字在原文中找不到：{0}".format(
            "、".join(missing_numbers[:4]))
    elif coverage >= 0.8 and not missing_numbers:
        verdict, reason = "verified", "关键措辞与数字均可在原文中找到"
    elif coverage >= 0.45:
        verdict, reason = "partially_supported", "部分措辞可对应，仍有 {0:.0%} 未命中".format(
            1 - coverage)
    else:
        verdict, reason = "insufficient", "原文重合度仅 {0:.0%}".format(coverage)

    return {"verdict": verdict, "reason": reason,
            "coverage": round(coverage, 2), "missing_numbers": missing_numbers}


def run(claims_dir: Path, sources_dir: Path, out_dir: Path) -> list:
    claims = load_claims(claims_dir)
    results = []
    for claim in claims:
        outcome = check_one(claim, sources_dir)
        results.append({**claim, **outcome})

    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    path = out_dir / "precheck_{0}.md".format(stamp)

    lines = [
        "# 规则预检报告（非模型判定）",
        "",
        "> 生成时间：{0}".format(datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
        "> 说明：本报告只做「数字是否出现 + 措辞重合度」的确定性预检，"
        "用于排序与筛查，不能替代校验官的最终 verdict。",
        "",
        "| claim_id | 预检结论 | 重合度 | 原文 | 理由 |",
        "| --- | --- | --- | --- | --- |",
    ]
    for item in results:
        lines.append("| {0} | {1} | {2} | {3} | {4} |".format(
            item["claim_id"], item["verdict"], item["coverage"],
            "、".join(item["source_ids"]) or "-", item["reason"]))
    lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")

    return results, path