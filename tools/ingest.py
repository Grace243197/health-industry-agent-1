"""
ingest.py · 资料入库脚本（V1 骨架）

功能：
  - 扫描 inbox/notes/*.md 与 inbox/pdfs/*.pdf
  - 去重（按标题 + 日期 + URL/路径 的简单哈希）
  - 为每份新来源分配递增编号 S###
  - 保存原件到 knowledge_base/sources/<SID>/raw.*
  - 提取文本到 knowledge_base/sources/<SID>/extracted.md
  - 写整理卡骨架到 knowledge_base/cards/<SID>.md
  - 追加到 knowledge_base/registry.jsonl
  - 读不到的链接写入 knowledge_base/pending_sources.md

使用：
  python tools/ingest.py --run-id <run_id>

不联网；不调用模型；不删除 inbox 原文件。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import sys
from datetime import date, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
INBOX = ROOT / "inbox"
KB = ROOT / "knowledge_base"
REGISTRY = KB / "registry.jsonl"
PENDING = KB / "pending_sources.md"
CARDS = KB / "cards"
SOURCES = KB / "sources"


def next_sid() -> str:
    """返回下一个可用的 S### 编号。"""
    max_n = 0
    if REGISTRY.exists():
        for line in REGISTRY.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            sid = rec.get("source_id", "")
            m = re.match(r"S(\d+)", sid)
            if m:
                max_n = max(max_n, int(m.group(1)))
    return f"S{max_n + 1:03d}"


def dedup_key(title: str, publish_date: str, url_or_path: str) -> str:
    """简单去重键：标题 + 日期 + 路径/URL 的 SHA1。"""
    blob = f"{title}\t{publish_date}\t{url_or_path}".encode("utf-8")
    return hashlib.sha1(blob).hexdigest()[:16]


def existing_dedup_keys() -> set[str]:
    keys: set[str] = set()
    if not REGISTRY.exists():
        return keys
    for line in REGISTRY.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            continue
        k = rec.get("dedup_key")
        if k:
            keys.add(k)
    return keys


def extract_md_text(path: Path) -> str:
    """读取 Markdown 正文；忽略 frontmatter（如有）。"""
    text = path.read_text(encoding="utf-8")
    # 简易 frontmatter 跳过
    if text.startswith("---"):
        end = text.find("---", 3)
        if end != -1:
            text = text[end + 3:].lstrip("\n")
    return text


def extract_pdf_text(path: Path) -> str:
    """用 pypdf 提取 PDF 文本；失败返回空字符串。"""
    try:
        from pypdf import PdfReader
    except ImportError:
        return "[pypdf 未安装，无法提取文本]"
    try:
        reader = PdfReader(str(path))
        parts = []
        for i, page in enumerate(reader.pages, 1):
            t = page.extract_text() or ""
            parts.append(f"<!-- page {i} -->\n{t}")
        return "\n\n".join(parts)
    except Exception as e:
        return f"[PDF 提取失败: {e}]"


def guess_meta_from_md(text: str, filename: str) -> dict:
    """从 Markdown 文本和文件名猜标题/日期。非常保守。"""
    title = ""
    for line in text.splitlines():
        s = line.strip()
        if s.startswith("# "):
            title = s[2:].strip()
            break
    if not title:
        title = Path(filename).stem
    # 从文件名猜日期：支持 20260916 或 2026年9月16日
    m = re.search(r"(20\d{2})[\D]?(\d{1,2})[\D]?(\d{1,2})", filename)
    if m:
        publish_date = f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"
    else:
        # 退而求其次，从正文前 20 行找 "录音时间：YYYY年M月D日" 之类
        publish_date = "unknown"
        for line in text.splitlines()[:20]:
            mm = re.search(r"(20\d{2})[\D非]?(\d{1,2})[\D非]?(\d{1,2})", line)
            if mm and ("录音" in line or "时间" in line or "日期" in line):
                publish_date = f"{mm.group(1)}-{int(mm.group(2)):02d}-{int(mm.group(3)):02d}"
                break
    return {"title": title, "publish_date": publish_date}


def write_card(sid: str, meta: dict, card_path: Path) -> None:
    card = f"""# {meta['title']}

- **source_id**: {sid}
- **type**: {meta.get('type', 'other')}
- **publisher**: {meta.get('publisher', 'unknown')}
- **publish_date**: {meta.get('publish_date', 'unknown')}
- **ingest_date**: {date.today().isoformat()}
- **url_or_path**: {meta.get('url_or_path', '')}
- **access**: {meta.get('access', 'public')}
- **evidence_level**: {meta.get('evidence_level', 'C')}
- **notes**: {meta.get('notes', '')}

## 摘要

TODO：由 source-collector 在后续步骤填写。

## 关键观点

-

## 支持片段（带原文位置）

-

## 适用范围 / 限制

-
"""
    card_path.write_text(card, encoding="utf-8")


def ingest_notes(run_id: str) -> list[dict]:
    """递归处理 inbox/notes/ 下所有 .md（忽略 README.md 与 图片/附件 目录）；返回新增记录列表。"""
    notes_dir = INBOX / "notes"
    if not notes_dir.exists():
        return []
    added = []
    existing = existing_dedup_keys()
    # 递归查找所有 .md；跳过 README、图片附件目录（按名字识别）
    skip_dir_names = {"图片和附件", "attachments", "images", "figures"}
    all_md: list[Path] = []
    for root, dirs, files in os.walk(notes_dir):
        dirs[:] = [d for d in dirs if d not in skip_dir_names]
        for fn in files:
            if fn.endswith(".md") and fn != "README.md":
                all_md.append(Path(root) / fn)
    all_md.sort()
    for md in all_md:
        text = extract_md_text(md)
        meta = guess_meta_from_md(text, md.name)
        meta.update(
            {
                "type": "meeting_note",
                "access": "internal",
                "evidence_level": "C",
                "notes": "会议纪要，未独立核实",
                "url_or_path": str(md.relative_to(ROOT)),
            }
        )
        dk = dedup_key(meta["title"], meta["publish_date"], meta["url_or_path"])
        if dk in existing:
            continue
        sid = next_sid()
        # 递增下一次
        existing.add(dk)
        dest_dir = SOURCES / sid
        dest_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(md, dest_dir / f"raw{md.suffix}")
        (dest_dir / "extracted.md").write_text(text, encoding="utf-8")
        card_path = CARDS / f"{sid}.md"
        write_card(sid, meta, card_path)
        rec = {
            "source_id": sid,
            "title": meta["title"],
            "type": meta["type"],
            "publisher": meta.get("publisher", "unknown"),
            "publish_date": meta["publish_date"],
            "ingest_date": date.today().isoformat(),
            "url_or_path": meta["url_or_path"],
            "domain": "成人睡眠健康",
            "theme": "睡眠监测",
            "topics": [],
            "access": meta["access"],
            "evidence_level": meta["evidence_level"],
            "notes": meta["notes"],
            "raw_path": f"knowledge_base/sources/{sid}/raw{md.suffix}",
            "extracted_path": f"knowledge_base/sources/{sid}/extracted.md",
            "card_path": f"knowledge_base/cards/{sid}.md",
            "dedup_key": dk,
        }
        with REGISTRY.open("a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        added.append(rec)
    return added


def write_collection(run_id: str, added: list[dict], failed: list[dict]) -> Path:
    runs_dir = ROOT / "runs" / run_id
    runs_dir.mkdir(parents=True, exist_ok=True)
    out = {
        "status": "ok" if not failed else "partial",
        "added": [r["source_id"] for r in added],
        "duplicates": [],
        "failed": failed,
        "pending": [],
        "tool_calls": 0,
        "timestamp": datetime.now().isoformat(),
    }
    path = runs_dir / "01_collection.json"
    path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-id", required=True)
    args = ap.parse_args()

    added = ingest_notes(args.run_id)
    out_path = write_collection(args.run_id, added, [])
    print(f"ingest: added {len(added)} sources; wrote {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
