#!/usr/bin/env python3
"""update_cards.py — 批量更新整理卡（消除 TODO）

读取每份来源的 extracted.md，自动提取摘要、关键观点、支持片段（带位置），
更新对应整理卡。S001/S002 标"AI生成会议纪要，未独立核实"。

用法:
  python tools/update_cards.py
"""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
KB = ROOT / "knowledge_base"
REGISTRY = KB / "registry.jsonl"
CARDS = KB / "cards"
SOURCES = KB / "sources"


def load_registry():
    recs = []
    for line in REGISTRY.read_text(encoding='utf-8').splitlines():
        line = line.strip()
        if not line or '__header__' in line:
            continue
        try:
            recs.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return recs


def extract_summary(text, max_len=400):
    """从 extracted.md 提取摘要。"""
    lines = text.split('\n')
    content_lines = []
    for line in lines:
        if line.startswith('#') or line.startswith('>') or line.startswith('---'):
            continue
        stripped = line.strip()
        if stripped and len(stripped) > 10:
            content_lines.append(stripped)
        if len(' '.join(content_lines)) > max_len:
            break
    summary = ' '.join(content_lines)
    if len(summary) > max_len:
        summary = summary[:max_len] + '...'
    return summary if summary else "来源内容已提取，详见 extracted.md。"


def extract_key_points(text, max_points=5):
    """提取关键观点（从列表项和段落首句）。"""
    points = []
    # 查找列表项
    for m in re.finditer(r'^[\s]*[-*]\s+(.+)$', text, re.MULTILINE):
        item = m.group(1).strip()
        if len(item) > 20:
            points.append(item)
        if len(points) >= max_points:
            break
    # 如果列表项不够，从段落补充
    if len(points) < 3:
        paras = re.split(r'\n\n+', text)
        for para in paras:
            para = para.strip()
            if para.startswith('#') or para.startswith('>') or para.startswith('---'):
                continue
            if len(para) > 50:
                first = re.split(r'[。！？\.\!\?]', para)[0]
                if len(first) > 20 and first not in points:
                    points.append(first + '。')
            if len(points) >= max_points:
                break
    return points if points else ["详见 extracted.md 全文。"]


def extract_excerpts(text, max_excerpts=3):
    """提取支持片段并标注位置。"""
    excerpts = []
    paragraphs = re.split(r'\n\n+', text)
    para_idx = 0
    for i, para in enumerate(paragraphs):
        para = para.strip()
        if para.startswith('#') or para.startswith('>') or para.startswith('---'):
            continue
        if len(para) > 60:
            para_idx += 1
            excerpt_text = para[:200]
            if len(para) > 200:
                excerpt_text += '...'
            excerpts.append({
                'text': excerpt_text,
                'location': f'段落 {i+1}',
            })
        if len(excerpts) >= max_excerpts:
            break
    return excerpts


def build_card(rec, text):
    """构建完整整理卡。"""
    sid = rec['source_id']
    title = rec.get('title', sid)
    source_type = rec.get('type', 'other')
    publisher = rec.get('publisher', 'unknown')
    notes = rec.get('notes', '')

    summary = extract_summary(text)
    key_points = extract_key_points(text)
    excerpts = extract_excerpts(text)

    # S001/S002 特殊标注
    if sid in ('S001', 'S002'):
        verification_status = 'unverified_meeting_note'
        limitation = '- AI生成会议纪要，未独立核实\n- 仅反映企业自述，不作为独立证据'
    elif rec.get('publisher') == 'Wikipedia':
        verification_status = 'pending'
        limitation = '- 百科条目，非同行评审\n- 需结合专业指南和论文验证'
    elif rec.get('type') == 'meeting_note':
        verification_status = 'unverified_meeting_note'
        limitation = '- 会议纪要，未独立核实'
    else:
        verification_status = 'pending'
        limitation = f'- {notes}' if notes else '- 待进一步验证'

    # 构建支持片段文本
    excerpts_text = ""
    for ex in excerpts:
        excerpts_text += f"\n- [{ex['location']}] {ex['text']}"
    if not excerpts_text:
        excerpts_text = "\n- 详见 extracted.md 全文"

    card = f"""---
source_id: {sid}
title: "{title}"
type: {source_type}
publisher: {publisher}
publish_date: {rec.get('publish_date', 'unknown')}
ingest_date: {rec.get('ingest_date', 'unknown')}
domain: {rec.get('domain', '成人睡眠健康')}
theme: {rec.get('theme', '睡眠监测')}
topics: {rec.get('topics', [])}
evidence_level: {rec.get('evidence_level', 'C')}
verification_status: {verification_status}
---

# {title}

## 摘要

{summary}

## 关键观点

{chr(10).join(f'- {p}' for p in key_points)}

## 支持片段与原文位置
{excerpts_text}

## 适用范围与限制

{limitation}

## 核验状态

{verification_status}
"""
    return card


def main():
    print("=" * 60)
    print("批量更新整理卡（消除 TODO）")
    print("=" * 60)

    recs = load_registry()
    print(f"来源记录: {len(recs)} 条")

    updated = 0
    for rec in recs:
        sid = rec.get('source_id', '')
        if rec.get('excluded') or rec.get('duplicate_of'):
            continue

        ext_path = ROOT / rec.get('extracted_path', '')
        card_path = ROOT / rec.get('card_path', '')

        if not ext_path.exists():
            print(f"  {sid}: 跳过（无 extracted.md）")
            continue

        text = ext_path.read_text(encoding='utf-8')
        card_content = build_card(rec, text)
        card_path.write_text(card_content, encoding='utf-8')
        updated += 1
        print(f"  {sid}: 已更新")

    print(f"\n更新完成: {updated} 张整理卡")
    return 0


if __name__ == '__main__':
    sys.exit(main())
