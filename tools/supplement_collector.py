"""
supplement_collector.py · 补充资料收集脚本

功能：
  - 分析当前知识库的覆盖度缺口
  - 自动生成补充收集建议
  - 支持联网搜索补充资料

使用：
  python tools/supplement_collector.py --run-id <run_id>
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
KB = ROOT / "knowledge_base"
REGISTRY = KB / "registry.jsonl"
RUNS = ROOT / "runs"


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


def analyze_coverage(recs: list[dict]) -> dict:
    """分析知识库覆盖度"""
    direction_count = {'RD': 0, 'CL': 0, 'AD': 0, 'PC': 0}
    type_count = {}
    evidence_count = {}
    
    for rec in recs:
        for topic in rec.get('topics', []):
            if topic in direction_count:
                direction_count[topic] += 1
        doc_type = rec.get('type', 'other')
        type_count[doc_type] = type_count.get(doc_type, 0) + 1
        level = rec.get('evidence_level', 'C')
        evidence_count[level] = evidence_count.get(level, 0) + 1
    
    return {
        'by_direction': direction_count,
        'by_type': type_count,
        'by_evidence': evidence_count,
        'total': len(recs),
    }


def identify_gaps(coverage: dict) -> list[dict]:
    """识别知识缺口"""
    gaps = []
    
    # 方向覆盖缺口
    direction_target = 6  # 每方向至少6份
    for direction, count in coverage['by_direction'].items():
        if count < direction_target:
            gaps.append({
                'type': 'direction_coverage',
                'direction': direction,
                'current': count,
                'target': direction_target,
                'priority': 'high' if count < 3 else 'medium',
                'suggestion': f'补充{direction}方向资料，当前{count}份，目标{direction_target}份'
            })
    
    # 资料类型缺口
    required_types = ['guideline', 'standard', 'job_posting', 'popular_science']
    for doc_type in required_types:
        if coverage['by_type'].get(doc_type, 0) == 0:
            gaps.append({
                'type': 'document_type',
                'document_type': doc_type,
                'priority': 'high',
                'suggestion': f'补充{doc_type}类型资料'
            })
    
    # A级证据缺口
    if coverage['by_evidence'].get('A', 0) == 0:
        gaps.append({
            'type': 'evidence_level',
            'level': 'A',
            'priority': 'medium',
            'suggestion': '补充A级证据（同行评审论文/系统综述）'
        })
    
    return gaps


def generate_search_queries(gaps: list[dict]) -> list[dict]:
    """根据缺口生成搜索建议"""
    queries = []
    
    direction_queries = {
        'RD': [
            'sleep monitoring technology validation study',
            'wearable sleep tracker accuracy clinical trial',
            'PSG vs HSAT comparative study',
        ],
        'CL': [
            'sleep disorder diagnosis guidelines China',
            'sleep clinic workflow best practices',
            'CPAP compliance intervention study',
        ],
        'AD': [
            'sleep center accreditation standards China',
            'sleep technologist certification requirements',
            'sleep lab quality management guidelines',
        ],
        'PC': [
            'sleep health public education guidelines',
            'consumer sleep device marketing regulation',
            'sleep apnea public awareness campaign',
        ],
    }
    
    for gap in gaps:
        if gap['type'] == 'direction_coverage':
            direction = gap['direction']
            for query in direction_queries.get(direction, []):
                queries.append({
                    'gap': gap,
                    'query': query,
                    'priority': gap['priority'],
                })
    
    return queries


def main() -> int:
    ap = argparse.ArgumentParser(description='补充资料收集')
    ap.add_argument('--run-id', required=True, help='运行ID')
    ap.add_argument('--fetch', action='store_true', help='实际抓取补充资料（调用 fetch_sources.py）')
    ap.add_argument('--dry-run', action='store_true', help='只输出补充计划，不抓取')
    args = ap.parse_args()

    print("=" * 60)
    print("补充资料收集分析")
    print("=" * 60)

    recs = load_registry()
    coverage = analyze_coverage(recs)

    print(f"\n当前知识库状态:")
    print(f"  资料总数: {coverage['total']}")
    print(f"  方向分布: {coverage['by_direction']}")
    print(f"  类型分布: {coverage['by_type']}")
    print(f"  证据等级: {coverage['by_evidence']}")

    gaps = identify_gaps(coverage)

    print(f"\n识别到 {len(gaps)} 个缺口:")
    for i, gap in enumerate(gaps, 1):
        print(f"  {i}. [{gap['priority'].upper()}] {gap['suggestion']}")

    queries = generate_search_queries(gaps)

    print(f"\n建议搜索查询 ({len(queries)} 条):")
    for i, q in enumerate(queries[:10], 1):
        print(f"  {i}. [{q['priority']}] {q['query']}")

    # 保存分析报告
    run_dir = RUNS / args.run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    report = {
        'run_id': args.run_id,
        'coverage': coverage,
        'gaps': gaps,
        'search_queries': queries[:20],
    }

    report_path = run_dir / 'supplement_analysis.json'
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f"\n分析报告已保存: {report_path}")

    # 如果指定 --fetch，调用 fetch_sources.py
    if args.fetch and not args.dry_run:
        print("\n" + "=" * 60)
        print("开始抓取补充资料...")
        import subprocess
        fetch_script = str(Path(__file__).resolve().parent / 'fetch_sources.py')
        cmd = [sys.executable, fetch_script, '--fetch', '--run-id', args.run_id]
        result = subprocess.run(cmd, capture_output=False)
        if result.returncode != 0:
            print(f"抓取失败，返回码: {result.returncode}")
            return result.returncode
        print("补充资料抓取完成")

    return 0


if __name__ == '__main__':
    sys.exit(main())
