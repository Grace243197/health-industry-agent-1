# -*- coding: utf-8 -*-
"""
知识库 Agent 命令行入口

  python run_cli.py --check
  python run_cli.py --task "预处理 research-collector-agent/sources/SRC001.md"
  python run_cli.py --task "把 SRC001 冻结进基线库，批准人：张三"
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
from agent.knowledge import KnowledgeBase    # noqa: E402

# 任务书写"6 个工具"：5 个业务工具 + 沙箱读写（save_file/read_file/list_dir）
EXPECTED_TOOLS = {"preprocess_doc", "search_knowledge", "freeze_source",
                  "list_sources", "archive_source",
                  "save_file", "read_file", "list_dir"}


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

    kb = KnowledgeBase(config.workspace, config.project_root,
                       config.project_path("COLLECTOR_SOURCES_DIR",
                                           "research-collector-agent/sources"))
    print("知识库目录 :")
    for label, path in (("staging", kb.staging_dir), ("frozen", kb.frozen_dir),
                        ("archive", kb.archive_dir)):
        count = len(list(path.glob("*.md"))) if path.is_dir() else 0
        print("  {0:<8}{1}（{2} 个 .md）".format(label + ":", path, count))
    records = kb.load_registry()
    print("  registry: {0}（{1} 条记录）".format(
        kb.registry_path, len(records)))
    if records:
        by_status = {}
        for record in records:
            by_status[record.get("status", "?")] = by_status.get(record.get("status", "?"), 0) + 1
        print("  状态分布: {0}".format(
            "，".join("{0}={1}".format(k, v) for k, v in sorted(by_status.items()))))

    if problems:
        print("\n[FAIL] 发现 {0} 个问题：".format(len(problems)))
        for item in problems:
            print("  - " + item)
        return 1
    print("\n[OK] 自检通过（未联网、未消耗额度）。")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="成人睡眠监测调研 · 知识库 Agent")
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

    agent = Agent(offline=args.offline)
    result = agent.run(args.task, verbose=args.verbose)
    print("\n[回答]\n" + result.answer)
    print("\n[运行摘要]")
    for key, value in result.summary():
        print("  {0}: {1}".format(key, value))
    return 0 if result.ok else 1


if __name__ == "__main__":
    sys.exit(main())