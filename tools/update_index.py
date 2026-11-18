"""
update_index.py · 更新知识库索引和统计

功能：
  - 统计知识库资料数量、方向分布、类型分布
  - 更新knowledge_base/README.md
  - 生成统计报告

使用：
  python tools/update_index.py
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
KB = ROOT / "knowledge_base"
REGISTRY = KB / "registry.jsonl"


def load_registry() -> list[dict]:
    """加载registry"""
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


def generate_stats(recs: list[dict]) -> dict:
    """生成统计信息"""
    stats = {
        'total': len(recs),
        'by_direction': Counter(),
        'by_type': Counter(),
        'by_evidence_level': Counter(),
        'by_access': Counter(),
    }
    
    for rec in recs:
        # 方向统计
        for topic in rec.get('topics', []):
            stats['by_direction'][topic] += 1
        
        # 类型统计
        doc_type = rec.get('type', 'other')
        stats['by_type'][doc_type] += 1
        
        # 证据等级统计
        level = rec.get('evidence_level', 'C')
        stats['by_evidence_level'][level] += 1
        
        # 访问权限统计
        access = rec.get('access', 'public')
        stats['by_access'][access] += 1
    
    return stats


def generate_readme(stats: dict, recs: list[dict]) -> str:
    """生成README内容"""
    direction_names = {
        'RD': '研究与开发 (R&D)',
        'CL': '临床诊疗与服务 (Clinics)',
        'AD': '管理与运营 (Administration)',
        'PC': '公共传播与健康沟通 (Public Communication)',
    }
    
    type_names = {
        'meeting_note': '会议纪要',
        'popular': '百科/科普',
        'popular_science': '科普文章',
        'guideline': '行业指南',
        'standard': '行业标准',
        'job_posting': '招聘信息',
        'academic': '学术论文',
        'other': '其他',
    }
    
    content = f"""# 本地知识库

> 最后更新: {date.today().isoformat()}

## 统计概览

| 指标 | 数量 |
|------|------|
| 资料总数 | {stats['total']} |
| 整理卡数量 | {stats['total']} |
| 主题页数量 | 9 |

## 方向分布

| 方向 | 资料数量 |
|------|----------|
"""
    
    for direction, name in direction_names.items():
        count = stats['by_direction'].get(direction, 0)
        content += f"| {name} | {count} |\n"
    
    content += f"""
## 资料类型分布

| 类型 | 数量 |
|------|------|
"""
    
    for doc_type, name in type_names.items():
        count = stats['by_type'].get(doc_type, 0)
        if count > 0:
            content += f"| {name} | {count} |\n"
    
    content += f"""
## 证据等级分布

| 等级 | 说明 | 数量 |
|------|------|------|
| A | 同行评审论文/系统综述 | {stats['by_evidence_level'].get('A', 0)} |
| B | 行业指南/标准 | {stats['by_evidence_level'].get('B', 0)} |
| C | 百科/科普/会议纪要 | {stats['by_evidence_level'].get('C', 0)} |

## 目录结构

```
knowledge_base/
├── registry.jsonl      # 来源登记表
├── README.md           # 本文件
├── pending_sources.md  # 待获取资料清单
├── cards/              # 整理卡（每份资料一张）
│   └── S###.md
├── sources/            # 原始资料
│   └── S###/
│       ├── raw.*       # 原件
│       └── extracted.md # 提取文本
└── topics/             # 主题页
    ├── RD_*.md         # R&D方向
    ├── CL_*.md         # 临床方向
    ├── AD_*.md         # 管理方向
    ├── PC_*.md         # 公共传播方向
    └── cross_direction_synthesis.md
```

## 来源清单

| 编号 | 标题 | 类型 | 方向 | 等级 |
|------|------|------|------|------|
"""
    
    for rec in recs:
        sid = rec.get('source_id', '')
        title = rec.get('title', '')[:40]
        doc_type = type_names.get(rec.get('type', 'other'), rec.get('type', 'other'))
        topics = ', '.join(rec.get('topics', [])) or '-'
        level = rec.get('evidence_level', 'C')
        content += f"| {sid} | {title} | {doc_type} | {topics} | {level} |\n"
    
    content += """
## 使用说明

1. **检索资料**: 使用 `tools/kb_search.py "关键词"` 搜索
2. **查看整理卡**: `knowledge_base/cards/S###.md`
3. **查看原文**: `knowledge_base/sources/S###/extracted.md`
4. **查看主题页**: `knowledge_base/topics/`

## 更新记录

- {date}: V2补充资料，新增22份资料（总计32份）
- 2026-10-26: V1初始入库，10份资料
"""
    
    return content


def main() -> int:
    print("=" * 60)
    print("更新知识库索引")
    print("=" * 60)
    
    recs = load_registry()
    stats = generate_stats(recs)
    
    print(f"\n资料总数: {stats['total']}")
    print(f"\n方向分布:")
    for direction, count in sorted(stats['by_direction'].items()):
        print(f"  {direction}: {count}")
    
    print(f"\n类型分布:")
    for doc_type, count in sorted(stats['by_type'].items()):
        print(f"  {doc_type}: {count}")
    
    print(f"\n证据等级分布:")
    for level, count in sorted(stats['by_evidence_level'].items()):
        print(f"  {level}: {count}")
    
    # 生成README
    readme_content = generate_readme(stats, recs)
    readme_path = KB / "README.md"
    readme_path.write_text(readme_content, encoding='utf-8')
    print(f"\n已更新: {readme_path}")
    
    # 生成统计报告
    report = {
        'date': date.today().isoformat(),
        'total_sources': stats['total'],
        'by_direction': dict(stats['by_direction']),
        'by_type': dict(stats['by_type']),
        'by_evidence_level': dict(stats['by_evidence_level']),
    }
    
    report_path = ROOT / "runs" / "261117-v2-supplement" / "kb_stats.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f"已生成: {report_path}")
    
    return 0


if __name__ == '__main__':
    sys.exit(main())
