"""
batch_ingest.py · 批量HTML资料入库脚本

功能：
  - 批量处理inbox目录下的HTML文件
  - 提取文本并转换为Markdown格式
  - 自动分配到对应方向（AD/PC/RD/CL）
  - 生成整理卡骨架
  - 更新registry.jsonl

使用：
  python tools/batch_ingest.py --run-id <run_id>
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

# 添加项目根目录到路径
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'tools'))

from html_extract import extract_text_from_html, extract_title_from_html

INBOX = ROOT / "inbox"
KB = ROOT / "knowledge_base"
REGISTRY = KB / "registry.jsonl"
CARDS = KB / "cards"
SOURCES = KB / "sources"

# URL到方向的映射
URL_DIRECTION_MAP = {
    # AD方向（管理与运营）
    'sleep_clinic': ['AD'],
    'sleep_center': ['AD'],
    'icsd': ['AD', 'CL'],
    'icd': ['AD', 'CL'],
    
    # PC方向（公共传播）
    'sleep_hygiene': ['PC', 'CL'],
    'cbti': ['PC', 'CL'],
    'chronotype': ['PC', 'RD'],
    'ess': ['PC', 'CL'],
    'mslt': ['PC', 'CL'],
    
    # RD方向（研究与开发）
    'psg': ['RD', 'CL'],
    'hsat': ['RD', 'CL'],
    'actigraphy': ['RD', 'CL'],
    'cpap': ['CL', 'PC'],
    'pap': ['CL', 'PC'],
    'sleep_cycle': ['RD', 'PC'],
}


def get_directions_from_filename(filename: str) -> list[str]:
    """从文件名推断方向"""
    filename_lower = filename.lower()
    for key, directions in URL_DIRECTION_MAP.items():
        if key in filename_lower:
            return directions
    return ['RD']  # 默认


def next_sid() -> str:
    """返回下一个可用的S###编号"""
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
    """简单去重键"""
    blob = f"{title}\t{publish_date}\t{url_or_path}".encode("utf-8")
    return hashlib.sha1(blob).hexdigest()[:16]


def existing_dedup_keys() -> set[str]:
    """获取已有的去重键"""
    keys = set()
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


def write_card(sid: str, meta: dict, card_path: Path) -> None:
    """生成整理卡"""
    card = f"""---
source_id: {sid}
title: "{meta['title']}"
type: {meta.get('type', 'popular')}
publisher: {meta.get('publisher', 'unknown')}
publish_date: {meta.get('publish_date', 'unknown')}
ingest_date: {meta.get('ingest_date', date.today().isoformat())}
domain: {meta.get('domain', '成人睡眠健康')}
theme: {meta.get('theme', '睡眠监测')}
topics: {meta.get('topics', [])}
evidence_level: {meta.get('evidence_level', 'C')}
verification_status: pending
---

# {meta['title']}

## 摘要

{meta.get('summary', '待补充。')}

## 关键观点

{meta.get('key_points', '- 待补充')}

## 支持片段（带原文位置）

{meta.get('excerpts', '- 待补充')}

## 适用范围 / 限制

{meta.get('limitations', '- 待验证')}

## 核验状态

- 待核验
"""
    card_path.write_text(card, encoding="utf-8")


def process_html_file(html_path: Path, run_id: str) -> dict | None:
    """处理单个HTML文件并入库"""

    # 读取HTML
    try:
        html_content = html_path.read_text(encoding='utf-8', errors='ignore')
    except Exception as e:
        print(f"  错误: 无法读取 {html_path.name}: {e}")
        return None

    # 提取标题和文本
    title = extract_title_from_html(html_content)
    text = extract_text_from_html(html_content)

    if len(text) < 100:
        print(f"  跳过: {html_path.name} (内容太短: {len(text)}字符)")
        return None

    # 推断方向
    topics = get_directions_from_filename(html_path.stem)

    # 生成元数据
    source_id = next_sid()
    dedup = dedup_key(title, "unknown", html_path.name)

    # 尝试从 fetch manifest 获取 canonical URL
    canonical_url = ""
    manifest_path = ROOT / "runs" / run_id / "01_fetch_manifest.json"
    if manifest_path.exists():
        try:
            manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
            for item in manifest.get('items', []):
                if item.get('source_id') == source_id:
                    canonical_url = item.get('final_url', '')
                    break
        except (json.JSONDecodeError, KeyError):
            pass

    # 如果 manifest 中没有，尝试从 HTML 中的 canonical link 提取
    if not canonical_url:
        import re
        match = re.search(r'<link[^>]+rel=["\']canonical["\'][^>]+href=["\']([^"\']+)["\']', html_content)
        if match:
            canonical_url = match.group(1)

    # 最后才用文件名推断（不再用文件名拼 Wikipedia URL）
    url_or_path = canonical_url if canonical_url else f"inbox/{html_path.name}"

    meta = {
        'source_id': source_id,
        'title': title,
        'type': 'popular',
        'publisher': 'unknown',
        'publish_date': 'unknown',
        'ingest_date': date.today().isoformat(),
        'url_or_path': url_or_path,
        'canonical_url': canonical_url,
        'domain': '成人睡眠健康',
        'theme': '睡眠监测',
        'topics': topics,
        'access': 'public',
        'evidence_level': 'C',
        'notes': '本地导入资料',
        'dedup_key': dedup,
        'fetch_status': 'fetched',
        'summary': f'{title}，从本地文件导入。',
        'key_points': '- 待补充',
        'excerpts': '- 待补充',
        'limitations': '- 需结合专业指南验证',
    }
    
    # 创建来源目录
    source_dir = SOURCES / source_id
    source_dir.mkdir(parents=True, exist_ok=True)
    
    # 保存原始HTML（重命名为.md以便阅读）
    extracted_path = source_dir / 'extracted.md'
    extracted_content = f"# {title}\n\n> 来源: Wikipedia\n> 入库日期: {date.today().isoformat()}\n\n---\n\n{text}"
    extracted_path.write_text(extracted_content, encoding='utf-8')
    
    # 保存raw（复制HTML）
    raw_path = source_dir / 'raw.html'
    shutil.copy2(html_path, raw_path)
    
    # 生成整理卡
    card_path = CARDS / f"{source_id}.md"
    write_card(source_id, meta, card_path)
    
    # 更新路径信息
    meta['raw_path'] = f"knowledge_base/sources/{source_id}/raw.html"
    meta['extracted_path'] = f"knowledge_base/sources/{source_id}/extracted.md"
    meta['card_path'] = f"knowledge_base/cards/{source_id}.md"
    
    # 追加到registry
    with REGISTRY.open('a', encoding='utf-8') as f:
        f.write(json.dumps(meta, ensure_ascii=False) + '\n')
    
    print(f"  入库: {source_id} - {title[:50]}...")
    print(f"    方向: {', '.join(topics)}")
    print(f"    字数: {len(text)}")
    
    return meta


def main() -> int:
    ap = argparse.ArgumentParser(description='批量HTML资料入库')
    ap.add_argument('--run-id', required=True, help='运行ID')
    ap.add_argument('--input-dir', default='inbox', help='输入目录')
    args = ap.parse_args()
    
    input_dir = ROOT / args.input_dir
    
    # 查找所有HTML文件
    html_files = list(input_dir.glob('temp_*.html'))
    
    if not html_files:
        print(f"未找到HTML文件: {input_dir}/temp_*.html")
        return 1
    
    print(f"找到 {len(html_files)} 个HTML文件")
    print("=" * 60)
    
    # 检查去重
    existing = existing_dedup_keys()
    
    added = []
    for html_file in sorted(html_files):
        print(f"\n处理: {html_file.name}")
        
        # 检查去重
        title = extract_title_from_html(html_file.read_text(encoding='utf-8', errors='ignore'))
        dedup = dedup_key(title, "unknown", html_file.name)
        
        if dedup in existing:
            print(f"  跳过: 已存在")
            continue
        
        result = process_html_file(html_file, args.run_id)
        if result:
            added.append(result)
            existing.add(result['dedup_key'])
    
    print("\n" + "=" * 60)
    print(f"入库完成: 新增 {len(added)} 份资料")
    
    # 写入收集报告
    runs_dir = ROOT / "runs" / args.run_id
    runs_dir.mkdir(parents=True, exist_ok=True)
    
    report = {
        'status': 'ok',
        'added': [r['source_id'] for r in added],
        'duplicates': [],
        'failed': [],
        'pending': [],
        'tool_calls': 0,
        'timestamp': datetime.now().isoformat(),
    }
    
    report_path = runs_dir / '01_collection.json'
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f"收集报告: {report_path}")
    
    return 0


if __name__ == '__main__':
    sys.exit(main())
