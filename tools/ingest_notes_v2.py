"""
ingest_notes_v2.py · Markdown资料入库脚本（V2）

功能：
  - 处理inbox/notes/目录下的Markdown文件
  - 自动识别资料类型（招聘/科普/指南/会议纪要）
  - 自动分配方向（AD/PC/RD/CL）
  - 生成整理卡
  - 更新registry.jsonl

使用：
  python tools/ingest_notes_v2.py --run-id <run_id>
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
CARDS = KB / "cards"
SOURCES = KB / "sources"

# 文件名关键词到方向的映射
KEYWORD_DIRECTION_MAP = {
    # AD方向
    '运营': ['AD'],
    '管理': ['AD'],
    '资质': ['AD'],
    '标准': ['AD', 'CL'],
    '规范': ['AD', 'CL'],
    '收费': ['AD'],
    '报销': ['AD'],
    '合规': ['AD'],
    
    # PC方向
    '科普': ['PC'],
    '宣教': ['PC'],
    '患者教育': ['PC'],
    '误区': ['PC'],
    '指南': ['PC', 'CL'],
    
    # 招聘
    '招聘': ['AD'],
    '岗位': ['AD'],
    '职位': ['AD'],
    
    # CL方向
    '临床': ['CL'],
    '诊断': ['CL'],
    '治疗': ['CL'],
    '监测': ['RD', 'CL'],
    '医师': ['CL'],
    '技师': ['CL'],
    
    # RD方向
    '技术': ['RD'],
    '设备': ['RD'],
    '算法': ['RD'],
    '传感器': ['RD'],
    '可穿戴': ['RD'],
}

# 文件名关键词到类型的映射
KEYWORD_TYPE_MAP = {
    '招聘': 'job_posting',
    '岗位': 'job_posting',
    '科普': 'popular_science',
    '宣教': 'popular_science',
    '指南': 'guideline',
    '标准': 'standard',
    '规范': 'standard',
    '纪要': 'meeting_note',
    '会议': 'meeting_note',
}


def guess_meta_from_filename(filename: str) -> dict:
    """从文件名推断元数据"""
    meta = {
        'type': 'other',
        'topics': ['RD'],  # 默认
        'evidence_level': 'C',
        'access': 'public',
        'notes': '',
    }
    
    # 推断类型
    for keyword, doc_type in KEYWORD_TYPE_MAP.items():
        if keyword in filename:
            meta['type'] = doc_type
            break
    
    # 推断方向
    topics = set()
    for keyword, directions in KEYWORD_DIRECTION_MAP.items():
        if keyword in filename:
            topics.update(directions)
    if topics:
        meta['topics'] = list(topics)
    
    # 特殊处理
    if '纪要' in filename or '会议' in filename:
        meta['type'] = 'meeting_note'
        meta['access'] = 'internal'
        meta['evidence_level'] = 'C'
        meta['notes'] = '会议纪要，未独立核实'
    
    if '指南' in filename or '标准' in filename:
        meta['evidence_level'] = 'B'
        meta['notes'] = '行业指南/标准，需结合实践验证'
    
    if '招聘' in filename:
        meta['type'] = 'job_posting'
        meta['notes'] = '招聘信息，反映岗位要求与市场情况'
    
    if '科普' in filename:
        meta['type'] = 'popular_science'
        meta['evidence_level'] = 'C'
        meta['notes'] = '科普文章，用于公众沟通参考'
    
    return meta


def extract_date_from_filename(filename: str) -> str:
    """从文件名提取日期"""
    # 支持格式：2026年10月、2026年10月15日、202610、20261015
    m = re.search(r'(20\d{2})[\D]?(\d{1,2})[\D]?(\d{1,2})?', filename)
    if m:
        year = m.group(1)
        month = m.group(2).zfill(2)
        day = m.group(3) if m.group(3) else '01'
        return f"{year}-{month}-{day.zfill(2)}"
    return 'unknown'


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


def extract_title_from_md(text: str, filename: str) -> str:
    """从Markdown文本或文件名提取标题"""
    for line in text.splitlines()[:10]:
        s = line.strip()
        if s.startswith('# '):
            return s[2:].strip()
    return Path(filename).stem


def write_card(sid: str, meta: dict, card_path: Path, text: str) -> None:
    """生成整理卡"""
    # 自动提取摘要（前200字）
    summary = text[:200].replace('\n', ' ') + '...'
    
    card = f"""# {meta['title']}

- **source_id**: {sid}
- **type**: {meta.get('type', 'other')}
- **publisher**: {meta.get('publisher', 'unknown')}
- **publish_date**: {meta.get('publish_date', 'unknown')}
- **ingest_date**: {meta.get('ingest_date', date.today().isoformat())}
- **url_or_path**: {meta.get('url_or_path', '')}
- **domain**: {meta.get('domain', '成人睡眠健康')}
- **theme**: {meta.get('theme', '睡眠监测')}
- **topics**: {meta.get('topics', [])}
- **access**: {meta.get('access', 'public')}
- **evidence_level**: {meta.get('evidence_level', 'C')}
- **notes**: {meta.get('notes', '')}

## 摘要

{summary}

## 关键观点

- TODO: 由source-collector补充

## 支持片段（带原文位置）

- TODO: 由source-collector补充

## 适用范围 / 限制

- {meta.get('notes', '需结合其他资料验证')}
"""
    card_path.write_text(card, encoding="utf-8")


def process_md_file(md_path: Path, run_id: str) -> dict | None:
    """处理单个Markdown文件并入库"""
    
    # 读取文件
    try:
        text = md_path.read_text(encoding='utf-8')
    except Exception as e:
        print(f"  错误: 无法读取 {md_path.name}: {e}")
        return None
    
    if len(text) < 50:
        print(f"  跳过: {md_path.name} (内容太短)")
        return None
    
    # 提取标题
    title = extract_title_from_md(text, md_path.name)
    
    # 从文件名推断元数据
    meta = guess_meta_from_filename(md_path.name)
    
    # 提取日期
    publish_date = extract_date_from_filename(md_path.name)
    
    # 生成元数据
    source_id = next_sid()
    dedup = dedup_key(title, publish_date, str(md_path.relative_to(ROOT)))
    
    meta.update({
        'source_id': source_id,
        'title': title,
        'publish_date': publish_date,
        'ingest_date': date.today().isoformat(),
        'url_or_path': str(md_path.relative_to(ROOT)),
        'domain': '成人睡眠健康',
        'theme': '睡眠监测',
        'dedup_key': dedup,
    })
    
    # 创建来源目录
    source_dir = SOURCES / source_id
    source_dir.mkdir(parents=True, exist_ok=True)
    
    # 保存原文
    extracted_path = source_dir / 'extracted.md'
    extracted_path.write_text(text, encoding='utf-8')
    
    raw_path = source_dir / f'raw{md_path.suffix}'
    shutil.copy2(md_path, raw_path)
    
    # 生成整理卡
    card_path = CARDS / f"{source_id}.md"
    write_card(source_id, meta, card_path, text)
    
    # 更新路径信息
    meta['raw_path'] = f"knowledge_base/sources/{source_id}/raw{md_path.suffix}"
    meta['extracted_path'] = f"knowledge_base/sources/{source_id}/extracted.md"
    meta['card_path'] = f"knowledge_base/cards/{source_id}.md"
    
    # 追加到registry
    with REGISTRY.open('a', encoding='utf-8') as f:
        f.write(json.dumps(meta, ensure_ascii=False) + '\n')
    
    print(f"  入库: {source_id} - {title[:50]}...")
    print(f"    类型: {meta['type']}")
    print(f"    方向: {', '.join(meta['topics'])}")
    print(f"    等级: {meta['evidence_level']}")
    
    return meta


def main() -> int:
    ap = argparse.ArgumentParser(description='Markdown资料入库（V2）')
    ap.add_argument('--run-id', required=True, help='运行ID')
    ap.add_argument('--input-dir', default='inbox/notes', help='输入目录')
    args = ap.parse_args()
    
    input_dir = ROOT / args.input_dir
    
    # 查找所有Markdown文件（排除README）
    md_files = [f for f in input_dir.glob('**/*.md') if f.name != 'README.md']
    
    if not md_files:
        print(f"未找到Markdown文件: {input_dir}/**/*.md")
        return 1
    
    print(f"找到 {len(md_files)} 个Markdown文件")
    print("=" * 60)
    
    # 检查去重
    existing = existing_dedup_keys()
    
    added = []
    for md_file in sorted(md_files):
        print(f"\n处理: {md_file.relative_to(input_dir)}")
        
        # 读取文件提取标题
        try:
            text = md_file.read_text(encoding='utf-8')
            title = extract_title_from_md(text, md_file.name)
        except:
            continue
        
        # 检查去重
        publish_date = extract_date_from_filename(md_file.name)
        dedup = dedup_key(title, publish_date, str(md_file.relative_to(ROOT)))
        
        if dedup in existing:
            print(f"  跳过: 已存在")
            continue
        
        result = process_md_file(md_file, args.run_id)
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
    
    report_path = runs_dir / '01_collection_notes.json'
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f"收集报告: {report_path}")
    
    return 0


if __name__ == '__main__':
    sys.exit(main())
