"""
fix_topic_pages.py · 修复主题页的未闭合 HTML 注释与重复核验段

背景：
  - kb_updater.py 曾写入未闭合的 `<!-- 原始更新记录...`，导致 Markdown 把正文当注释隐藏。
  - 多次运行会重复追加 `## 核验备注`，产生噪音。

用法：
  python tools/fix_topic_pages.py --dry-run
  python tools/fix_topic_pages.py --apply
"""

from __future__ import annotations

import argparse
import re
import shutil
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TOPICS = ROOT / "knowledge_base" / "topics"
ARCHIVE = TOPICS / "archive"

NOTE = """
## 核验状态

- 详细结果：`runs/261117-v2-full/03_verification.json`
- 当前限制：现有核验仅按证据等级判定，尚未逐条对照原文；S011–S032 与岗位页未覆盖。
- 完成真实核验后，请用 `tools/kb_updater.py` 重新生成本节。
"""


def fix_content(text: str) -> tuple[str, dict]:
    original = text
    removed_header = 0
    removed_sections = 0

    # 1. 去掉未闭合的“原始更新记录”注释，以及它后面被吞掉的归档行
    out = []
    skip_archive_line = False
    seen_archive = False
    for line in text.splitlines():
        stripped = line.strip()

        if stripped.startswith("<!-- 原始更新记录"):
            removed_header += 1
            skip_archive_line = True
            continue

        if skip_archive_line and stripped.startswith("> 旧版本归档："):
            removed_header += 1
            skip_archive_line = False
            continue
        skip_archive_line = False

        # 只保留第一个有效的归档引用，避免重复
        if stripped.startswith("> 旧版本归档："):
            if seen_archive:
                removed_header += 1
                continue
            seen_archive = True

        out.append(line)

    text = "\n".join(out)
    text = re.sub(r"\n{3,}", "\n\n", text)

    # 2. 删除已有的“核验备注/核验状态”段（可能重复了多次）
    parts = re.split(r"(?m)^## ", text)
    kept = []
    for part in parts:
        if part.startswith("核验备注") or part.startswith("核验状态"):
            removed_sections += 1
            continue
        kept.append(part)
    text = "## ".join(kept).rstrip() + "\n"

    # 3. 追加一个格式正确、内容诚实的核验状态段
    text = text + NOTE

    unclosed = text.count("<!--") - text.count("-->")
    return text, {
        "removed_header_lines": removed_header,
        "removed_sections": removed_sections,
        "unclosed_comments": unclosed,
        "changed": text != original,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="修复主题页注释与重复核验段")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    if not args.dry_run and not args.apply:
        ap.error("请指定 --dry-run 或 --apply")

    files = sorted(p for p in TOPICS.glob("*.md") if p.is_file())
    # 岗位页没有这类注释问题，跳过以免误改
    files = [p for p in files if not p.name.startswith("job_")]

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    changed = 0

    for path in files:
        text = path.read_text(encoding="utf-8")
        new_text, info = fix_content(text)

        if not info["changed"]:
            print(f"{path.name}: no change")
            continue

        changed += 1
        print(
            f"{path.name}: header={info['removed_header_lines']} "
            f"sections={info['removed_sections']} "
            f"unclosed_after={info['unclosed_comments']}"
        )

        if args.apply:
            ARCHIVE.mkdir(parents=True, exist_ok=True)
            backup = ARCHIVE / f"pre_v2fix_{stamp}_{path.name}"
            shutil.copy2(path, backup)
            path.write_text(new_text, encoding="utf-8")
            print(f"  archived -> {backup.relative_to(ROOT)}")

    mode = "Applied" if args.apply else "Dry-run"
    print(f"\n{mode}: {changed} file(s) changed.")
    if not args.apply:
        print("Use --apply to write changes.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
