"""
kb_search.py · 本地知识库检索（V1 骨架）

功能：
  - 在 knowledge_base/sources/*/extracted.md 与 cards/*.md 中做关键词搜索
  - 返回来源编号 + 位置 + 片段
  - 可按方向（RD/CL/AD/PC）过滤（依据 registry.jsonl 的 topics 字段）

使用：
  python tools/kb_search.py "关键词" [--direction RD] [--limit 10]

不联网；不调用模型。
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
KB = ROOT / "knowledge_base"
REGISTRY = KB / "registry.jsonl"
SOURCES = KB / "sources"
CARDS = KB / "cards"


def load_registry() -> list[dict]:
    if not REGISTRY.exists():
        return []
    recs = []
    for line in REGISTRY.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            recs.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return recs


def filter_by_direction(recs: list[dict], direction: str | None) -> list[dict]:
    if not direction:
        return recs
    return [r for r in recs if direction in r.get("topics", [])]


def snippet(text: str, keyword: str, context: int = 120) -> list[dict]:
    """返回 keyword 在 text 中的若干片段（大小写不敏感）。"""
    kw = re.compile(re.escape(keyword), re.IGNORECASE)
    hits = []
    for m in kw.finditer(text):
        start = max(0, m.start() - context)
        end = min(len(text), m.end() + context)
        hits.append(
            {
                "start": start,
                "end": end,
                "text": text[start:end].replace("\n", " "),
            }
        )
        if len(hits) >= 3:
            break
    return hits


def search(keyword: str, direction: str | None, limit: int) -> list[dict]:
    recs = filter_by_direction(load_registry(), direction)
    results: list[dict] = []
    for rec in recs:
        if rec.get("source_id", "").startswith("__"):
            continue
        ext_path = ROOT / rec.get("extracted_path", "")
        card_path = ROOT / rec.get("card_path", "")
        hit = {"source_id": rec["source_id"], "title": rec.get("title", ""), "matches": []}
        if ext_path.exists():
            text = ext_path.read_text(encoding="utf-8")
            for s in snippet(text, keyword):
                hit["matches"].append(
                    {"file": str(ext_path.relative_to(ROOT)), **s, "kind": "extracted"}
                )
        if card_path.exists():
            text = card_path.read_text(encoding="utf-8")
            for s in snippet(text, keyword):
                hit["matches"].append(
                    {"file": str(card_path.relative_to(ROOT)), **s, "kind": "card"}
                )
        if hit["matches"]:
            results.append(hit)
        if len(results) >= limit:
            break
    return results


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("keyword")
    ap.add_argument("--direction", default=None)
    ap.add_argument("--limit", type=int, default=10)
    args = ap.parse_args()

    results = search(args.keyword, args.direction, args.limit)
    print(json.dumps(results, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
