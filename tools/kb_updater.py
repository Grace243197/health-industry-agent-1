#!/usr/bin/env python3
"""kb_updater.py — 知识库主题页更新脚本（幂等）

功能：
  - 根据核验结果更新主题页的"核验状态"段
  - 归档旧版本
  - 幂等：先删除旧核验段再写入新段
  - 不写未闭合注释

用法:
  python tools/kb_updater.py --run-id <run_id>
"""
import argparse
import json
import os
import re
import shutil
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
KB = ROOT / "knowledge_base"
TOPICS = KB / "topics"
ARCHIVE = TOPICS / "archive"
RUNS = ROOT / "runs"

ALL_TOPIC_FILES = [
    "RD_sensors_and_algorithms.md",
    "RD_wearables_and_technologies.md",
    "CL_psg_hsAT_workflow.md",
    "CL_professional_collaboration.md",
    "AD_service_requirements.md",
    "AD_compliance_and_quality.md",
    "PC_public_communication.md",
    "PC_evidence_and_misleading.md",
    "cross_direction_synthesis.md",
]


def archive_topic(topic_path, run_id):
    """归档主题页旧版本"""
    ARCHIVE.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime('%Y%m%d_%H%M%S')
    archive_name = f"{topic_path.stem}_{ts}.md"
    archive_path = ARCHIVE / archive_name
    shutil.copy2(topic_path, archive_path)
    return archive_path


def remove_old_verification(content):
    """删除旧的核验段和未闭合注释，保证幂等"""
    # 删除 ## 核验状态 / ## 核验备注 段
    content = re.sub(r'\n##\s*核验(?:状态|备注)[^\n]*\n.*?(?=\n##\s|\Z)', '', content, flags=re.DOTALL)
    # 删除未闭合的 HTML 注释块（<!-- ... 没有 --> 的）
    content = re.sub(r'<!--\s*原始更新记录[^>]*$', '', content, flags=re.DOTALL)
    # 删除重复的核验 HTML 注释行
    content = re.sub(r'\n<!--\s*核验:.*?-->', '', content)
    return content.rstrip()


def build_verification_section(results_for_page):
    """构建核验状态段"""
    if not results_for_page:
        return "\n\n## 核验状态\n\n暂无核验结果。\n"

    supported = sum(1 for r in results_for_page if r['verdict'] == 'supported')
    partial = sum(1 for r in results_for_page if r['verdict'] == 'partially_supported')
    not_sup = sum(1 for r in results_for_page if r['verdict'] == 'not_supported')
    unverified = sum(1 for r in results_for_page if r['verdict'] == 'unverifiable')

    section = f"\n\n## 核验状态\n\n"
    section += f"共 {len(results_for_page)} 条判断："
    section += f"supported={supported}, partially_supported={partial}, not_supported={not_sup}, unverifiable={unverified}\n\n"

    # 详细表格
    section += "| 判断摘要 | 来源 | 判定 | 原因 |\n"
    section += "|----------|------|------|------|\n"
    for r in results_for_page:
        claim_short = r['claim'][:50] + ('...' if len(r['claim']) > 50 else '')
        sources = ', '.join(r.get('source_ids', []))
        section += f"| {claim_short} | {sources} | {r['verdict']} | {r.get('reason', '')} |\n"

    return section


def update_topic_page(topic_path, results_for_page, run_id):
    """更新单个主题页"""
    # 归档
    archive_path = archive_topic(topic_path, run_id)

    # 读取内容
    content = topic_path.read_text(encoding='utf-8')

    # 删除旧核验段
    content = remove_old_verification(content)

    # 更新"最后更新"行
    content = re.sub(
        r'>\s*最后更新：[^\n]*',
        f'> 最后更新：{datetime.now().strftime("%Y-%m-%d")} · run_id: {run_id}',
        content
    )

    # 添加新核验段
    content += build_verification_section(results_for_page)
    content += "\n"

    # 写回
    topic_path.write_text(content, encoding='utf-8')

    return {
        'topic': topic_path.name,
        'archive': str(archive_path.relative_to(ROOT)),
        'claims_count': len(results_for_page),
    }


def main():
    ap = argparse.ArgumentParser(description='知识库主题页更新')
    ap.add_argument('--run-id', required=True, help='运行 ID')
    args = ap.parse_args()

    run_dir = RUNS / args.run_id
    ver_path = run_dir / '03_verification.json'

    if not ver_path.exists():
        print(f"错误: 核验报告不存在: {ver_path}")
        return 1

    verification = json.loads(ver_path.read_text(encoding='utf-8'))
    results = verification.get('results', [])
    print(f"加载 {len(results)} 条核验结果")

    # 按页面分组
    by_page = {}
    for r in results:
        page = r.get('page', 'unknown')
        if page not in by_page:
            by_page[page] = []
        by_page[page].append(r)

    updates = []
    for topic_file in ALL_TOPIC_FILES:
        topic_path = TOPICS / topic_file
        if not topic_path.exists():
            print(f"  跳过: {topic_file} (不存在)")
            continue

        page_results = by_page.get(topic_file, [])
        print(f"  更新: {topic_file} ({len(page_results)} 条判断)")
        update = update_topic_page(topic_path, page_results, args.run_id)
        updates.append(update)

    # 写更新日志
    log_path = run_dir / '05_kb_update.md'
    log = f"# 知识库更新日志\n\n"
    log += f"**运行ID**: {args.run_id}\n"
    log += f"**更新时间**: {datetime.now().isoformat()}\n\n"
    log += f"更新主题页: {len(updates)}\n\n"
    log += "| 主题页 | 归档位置 | 判断数 |\n"
    log += "|--------|----------|--------|\n"
    for u in updates:
        log += f"| {u['topic']} | {u['archive']} | {u['claims_count']} |\n"

    log_path.write_text(log, encoding='utf-8')
    print(f"\n更新日志: {log_path}")
    return 0


if __name__ == '__main__':
    sys.exit(main())
