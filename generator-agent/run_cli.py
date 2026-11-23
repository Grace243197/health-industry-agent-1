# -*- coding: utf-8 -*-
"""
生成 Agent 命令行入口

  python run_cli.py --check
  python run_cli.py --task "生成成人睡眠监测技术现状报告"
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from agent import Agent                      # noqa: E402
from agent.config import Config              # noqa: E402
from agent.tools import preflight            # noqa: E402

EXPECTED_TOOLS = {"search_knowledge", "load_source_cards", "read_file",
                  "list_dir", "save_report"}
UPSTREAM = {
    "固化基线": ("KB_FROZEN_DIR", "knowledge-agent/knowledge_base/frozen"),
    "基线条目": ("KB_REGISTRY", "knowledge-agent/knowledge_base/registry.jsonl"),
    "来源卡": ("COLLECTOR_SOURCES_DIR", "research-collector-agent/sources"),
}


def _describe_path(path: Path) -> str:
    if path.is_file():
        return "{0}（文件，{1} 字节）".format(path, path.stat().st_size)
    if path.is_dir():
        count = len([p for p in path.rglob("*.md") if p.is_file()])
        return "{0}（目录，{1} 个 .md）".format(path, count)
    return "{0}（不存在）".format(path)


def do_check() -> int:
    config = Config()
    agent = Agent(config=config, offline=True)
    print(agent.describe())

    names = set(agent.tools.names())
    problems = []
    if names != EXPECTED_TOOLS:
        problems.append("工具集与任务书不一致：多出 {0}，缺少 {1}".format(
            names - EXPECTED_TOOLS, EXPECTED_TOOLS - names))
    for name in names:
        if name not in agent.system_prompt:
            problems.append("提示词里没有提到已注册工具：{0}".format(name))

    print("上游目录 :")
    for label, (key, default) in UPSTREAM.items():
        print("  {0:<8}{1}".format(label + ":", _describe_path(config.project_path(key, default))))

    ok, message = preflight(config)
    print("\n双源检查 : {0}".format("通过" if ok else "未通过"))
    if not ok:
        print(message)

    if problems:
        print("\n[FAIL] 发现 {0} 个问题：".format(len(problems)))
        for item in problems:
            print("  - " + item)
        return 1
    print("\n[OK] 自检通过（未联网、未消耗额度）。")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="成人睡眠监测调研 · 生成 Agent")
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--task", default=None)
    parser.add_argument("--offline", action="store_true")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    if args.check:
        return do_check()
    if not args.task:
        parser.print_help()
        return 2

    config = Config()
    ok, message = preflight(config)
    if not ok:
        print(message)
        return 3
    print(message)

    agent = Agent(config=config, offline=args.offline)
    result = agent.run(args.task, verbose=args.verbose)

    print("\n[回答]\n" + result.answer)
    print("\n[运行摘要]")
    for key, value in result.summary():
        print("  {0}: {1}".format(key, value))
    return 0 if result.ok else 1


if __name__ == "__main__":
    sys.exit(main())