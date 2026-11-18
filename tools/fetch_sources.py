#!/usr/bin/env python3
"""fetch_sources.py — 资料采集工具

从 registry.jsonl 读取 fetch_status=pending 的来源，抓取内容并入库。

用法:
  python tools/fetch_sources.py --dry-run          # 只列出待抓取计划
  python tools/fetch_sources.py --fetch             # 实际抓取
  python tools/fetch_sources.py --fetch --run-id 261117-v2-fix  # 指定 run_id

支持:
  - Wikipedia REST API: /api/rest_v1/page/html/<Title>
  - 通用 URL: urllib 直连
  - 30s 超时, 2 次重试, 自定义 User-Agent
  - 失败写入 pending_sources.md
  - 抓取清单写入 runs/<run_id>/01_fetch_manifest.json
"""
import argparse
import hashlib
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
KB = ROOT / "knowledge_base"
REGISTRY = KB / "registry.jsonl"
RUNS = ROOT / "runs"

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
TIMEOUT = 30
MAX_RETRIES = 2

WIKI_REST = "https://en.wikipedia.org/api/rest_v1/page/html"


def load_registry():
    entries = []
    with open(REGISTRY, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                entries.append(json.loads(line))
    return entries


def save_registry(entries):
    with open(REGISTRY, "w", encoding="utf-8") as f:
        for e in entries:
            f.write(json.dumps(e, ensure_ascii=False) + "\n")


def get_pending(entries):
    pending = []
    for e in entries:
        if e.get("source_id") == "__header__":
            continue
        if e.get("excluded") or e.get("duplicate_of"):
            continue
        if e.get("fetch_status") == "pending":
            pending.append(e)
    return pending


def resolve_url(entry):
    """Determine the actual fetch URL for a source."""
    canonical = entry.get("canonical_url", "")
    url_or_path = entry.get("url_or_path", "")

    if canonical and canonical.startswith("http"):
        url = canonical
    elif url_or_path and url_or_path.startswith("http"):
        url = url_or_path
    else:
        return None

    # Convert Wikipedia web URLs to REST API URLs for better content extraction
    wiki_match = re.match(r"https://en\.wikipedia\.org/wiki/(.+)", url)
    if wiki_match:
        title = urllib.parse.unquote(wiki_match.group(1))
        return f"{WIKI_REST}/{title}"

    return url


def fetch_url(url, retries=MAX_RETRIES):
    """Fetch URL content with retries. Returns (html, final_url, status_code, sha256, elapsed)."""
    import ssl
    import urllib.parse

    headers = {"User-Agent": USER_AGENT, "Accept": "text/html,application/xhtml+xml"}
    sha = None

    # Create SSL context that handles certificate issues
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE

    for attempt in range(retries + 1):
        try:
            req = urllib.request.Request(url, headers=headers)
            t0 = time.time()
            resp = urllib.request.urlopen(req, timeout=TIMEOUT, context=ctx)
            html = resp.read()
            elapsed = round(time.time() - t0, 2)
            final_url = resp.geturl()
            status = resp.getcode()
            sha = hashlib.sha256(html).hexdigest()
            return html.decode("utf-8", errors="replace"), final_url, status, sha, elapsed
        except urllib.error.HTTPError as e:
            if e.code in (404, 403) and attempt < retries:
                time.sleep(1)
                continue
            return None, url, e.code, None, 0
        except Exception as e:
            if attempt < retries:
                time.sleep(1)
                continue
            return None, url, 0, None, 0
    return None, url, 0, None, 0


def extract_and_save(entry, html_content):
    """Extract text from HTML and save as extracted.md + raw.html."""
    sid = entry["source_id"]
    src_dir = KB / "sources" / sid
    src_dir.mkdir(parents=True, exist_ok=True)

    # Save raw HTML
    raw_path = src_dir / "raw.html"
    raw_path.write_text(html_content, encoding="utf-8")

    # Extract text using html_extract
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from html_extract import extract_text_from_html, extract_title_from_html

    title = extract_title_from_html(html_content)
    text = extract_text_from_html(html_content)

    extracted = f"# {title}\n\n> Source: {entry.get('canonical_url', entry.get('url_or_path', ''))}\n> Fetched: {datetime.now().strftime('%Y-%m-%d')}\n\n---\n\n{text}"
    ext_path = src_dir / "extracted.md"
    ext_path.write_text(extracted, encoding="utf-8")

    return str(raw_path.relative_to(ROOT)), str(ext_path.relative_to(ROOT)), title, len(text)


def generate_card(entry, title, text_len):
    """Generate a knowledge card for the source."""
    sid = entry["source_id"]
    cards_dir = KB / "cards"
    cards_dir.mkdir(parents=True, exist_ok=True)

    card = f"""---
source_id: {sid}
title: "{entry.get('title', title)}"
type: {entry.get('type', 'unknown')}
publisher: {entry.get('publisher', 'unknown')}
publish_date: {entry.get('publish_date', 'unknown')}
ingest_date: {entry.get('ingest_date', 'unknown')}
domain: {entry.get('domain', 'unknown')}
theme: {entry.get('theme', 'unknown')}
topics: {entry.get('topics', [])}
evidence_level: {entry.get('evidence_level', 'C')}
verification_status: pending
---

# {entry.get('title', title)}

## 摘要
{entry.get('title', title)} — {entry.get('publisher', 'unknown')} 发布的{entry.get('type', 'unknown')}类型资料。

## 关键观点
- 待补充（由 update_cards 自动提取）

## 支持片段与原文位置
- 待补充

## 适用范围与限制
- {entry.get('notes', 'unknown')}

## 核验状态
- 待核验
"""
    card_path = cards_dir / f"{sid}.md"
    card_path.write_text(card, encoding="utf-8")
    return str(card_path.relative_to(ROOT))


def write_pending(pending_entries, failed_items):
    """Write pending_sources.md for failed items."""
    md = "# 待获取来源\n\n"
    md += f"更新时间: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n\n"
    if failed_items:
        md += "## 抓取失败\n\n"
        for item in failed_items:
            md += f"- **{item['source_id']}**: {item['title']} — HTTP {item.get('status', 'error')}\n"
            md += f"  URL: {item.get('url', 'N/A')}\n"
    md += "\n## 待人工处理\n\n"
    md += "（暂无）\n"

    pending_path = KB / "pending_sources.md"
    pending_path.write_text(md, encoding="utf-8")
    return str(pending_path)


def main():
    ap = argparse.ArgumentParser(description="资料采集工具")
    ap.add_argument("--dry-run", action="store_true", help="只列出待抓取计划")
    ap.add_argument("--fetch", action="store_true", help="实际抓取")
    ap.add_argument("--run-id", type=str, default=None, help="运行 ID")
    ap.add_argument("--source-ids", type=str, nargs="*", help="只处理指定来源 ID")
    args = ap.parse_args()

    if not args.dry_run and not args.fetch:
        ap.print_help()
        return 1

    entries = load_registry()
    pending = get_pending(entries)

    if args.source_ids:
        pending = [p for p in pending if p["source_id"] in args.source_ids]

    print(f"待抓取来源: {len(pending)} 条")
    for p in pending:
        url = resolve_url(p)
        print(f"  {p['source_id']}: {p['title']} -> {url}")

    if args.dry_run:
        print("\n[DRY RUN] 以上为抓取计划，使用 --fetch 执行")
        return 0

    if not args.fetch:
        return 0

    # Setup run directory
    run_id = args.run_id or datetime.now().strftime("%y%m%d-%H%M%S-fetch")
    run_dir = RUNS / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    manifest = []
    failed = []
    success_count = 0

    for p in pending:
        sid = p["source_id"]
        url = resolve_url(p)
        if not url:
            print(f"  [{sid}] 无有效 URL，跳过")
            failed.append({"source_id": sid, "title": p["title"], "status": "no_url"})
            continue

        print(f"  [{sid}] 抓取: {url[:80]}...")
        html, final_url, status, sha, elapsed = fetch_url(url)

        if html is None or status != 200:
            print(f"    FAIL: HTTP {status}")
            failed.append({"source_id": sid, "title": p["title"], "url": url, "status": status})
            manifest.append({
                "source_id": sid, "url": url, "final_url": final_url,
                "status": status, "sha256": None, "elapsed": elapsed,
                "success": False, "timestamp": datetime.now().isoformat()
            })
            continue

        # Save and extract
        raw_rel, ext_rel, title, text_len = extract_and_save(p, html)
        card_rel = generate_card(p, title, text_len)

        # Update registry entry
        for i, e in enumerate(entries):
            if e.get("source_id") == sid:
                entries[i]["fetch_status"] = "fetched"
                entries[i]["raw_path"] = raw_rel.replace("\\", "/")
                entries[i]["extracted_path"] = ext_rel.replace("\\", "/")
                entries[i]["card_path"] = card_rel.replace("\\", "/")
                entries[i]["canonical_url"] = final_url
                break

        print(f"    OK: {text_len} chars, sha256={sha[:12]}...")
        success_count += 1
        manifest.append({
            "source_id": sid, "url": url, "final_url": final_url,
            "status": status, "sha256": sha, "elapsed": elapsed,
            "success": True, "text_chars": text_len,
            "timestamp": datetime.now().isoformat()
        })

    # Save manifest
    manifest_path = run_dir / "01_fetch_manifest.json"
    manifest_path.write_text(json.dumps({
        "run_id": run_id, "total": len(pending),
        "success": success_count, "failed": len(failed),
        "items": manifest
    }, ensure_ascii=False, indent=2), encoding="utf-8")

    # Write pending_sources.md
    write_pending(pending, failed)

    # Save updated registry
    save_registry(entries)

    print(f"\n完成: 成功 {success_count}/{len(pending)}, 失败 {len(failed)}")
    print(f"Manifest: {manifest_path}")
    if failed:
        print(f"失败清单: {KB / 'pending_sources.md'}")

    return 0


if __name__ == "__main__":
    import urllib.parse
    sys.exit(main())
