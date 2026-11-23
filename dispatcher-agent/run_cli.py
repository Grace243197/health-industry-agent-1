# -*- coding: utf-8 -*-
"""
调度 Agent 命令行入口

  python run_cli.py --check
  python run_cli.py --task "调研成人睡眠监测行业并出一份带证据索引的报告"
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

# 任务书写"6 个工具"，其中 read_file/list_dir 合称一项，实际注册 7 个函数
EXPECTED_TOOLS = {"run_collector", "run_knowledge", "run_generator", "run_verifier",
                  "list_agents", "read_file", "list_dir"}

DOWNSTREAM = (
    ("采集", "COLLECTOR_RUN_CLI", "research-collector-agent/run_cli.py"),
    ("知识库", "KNOWLEDGE_RUN_CLI", "knowledge-agent/run_cli.py"),
    ("生成", "GENERATOR_RUN_CLI", "generator-agent/run_cli.py"),
    ("校验", "VERIFIER_RUN_CLI", "verify-agent/run_cli.py"),
)


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

    print("下游入口 :")
    missing = 0
    for label, key, default in DOWNSTREAM:
        path = config.project_path(key, default)
        exists = path.is_file()
        missing += 0 if exists else 1
        print("  {0:<6}{1}  {2}".format(label, path, "存在" if exists else "缺失"))

    print("审计目录 : {0}".format(config.extra_dirs.get("audit")))

    if problems:
        print("\n[FAIL] 发现 {0} 个问题：".format(len(problems)))
        for item in problems:
            print("  - " + item)
        return 1

    if missing:
        print("\n[WARN] 有 {0} 个下游入口缺失：调度会如实报「调用失败」，不会伪造产出。".format(missing))
    print("\n[OK] 自检通过（未联网、未消耗额度）。")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="成人睡眠监测调研 · 总调度")
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