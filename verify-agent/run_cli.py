# -*- coding: utf-8 -*-
"""
校验 Agent 命令行入口

  python run_cli.py --check
  python run_cli.py --precheck                     # 规则版预检，不调用模型
  python run_cli.py --task "校验 claims 里的断言"   # 模型校验（离线可用假模型）
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
from precheck import run as run_precheck     # noqa: E402

EXPECTED_TOOLS = {"grep_source", "read_file", "list_dir", "save_file"}


def _count(path: Path) -> int:
    return len([p for p in path.rglob("*") if p.is_file()]) if path.is_dir() else 0


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

    print("工作目录 :")
    for key, path in config.extra_dirs.items():
        print("  {0:<14}{1}（{2} 个文件）".format(key + ":", path, _count(path)))

    if problems:
        print("\n[FAIL] 发现 {0} 个问题：".format(len(problems)))
        for item in problems:
            print("  - " + item)
        return 1
    print("\n[OK] 自检通过（未联网、未消耗额度）。")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="成人睡眠监测调研 · 证据校验 Agent")
    parser.add_argument("--check", action="store_true", help="打印自检报告")
    parser.add_argument("--precheck", action="store_true", help="规则版预检（不调用模型）")
    parser.add_argument("--task", default=None, help="自然语言校验任务")
    parser.add_argument("--offline", action="store_true", help="强制离线假模型")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    if args.check:
        return do_check()

    config = Config()

    if args.precheck:
        results, path = run_precheck(config.extra_dirs["claims"],
                                     config.extra_dirs["sources"],
                                     config.extra_dirs["verifications"])
        if not results:
            print("claims/ 下没有可预检的断言。先放入 claims_*.json 或 CLM*.md。")
            return 1
        print("{0:<16}{1:<22}{2:<8}{3}".format("claim_id", "预检结论", "重合度", "理由"))
        for item in results:
            print("{0:<16}{1:<22}{2:<8}{3}".format(
                item["claim_id"], item["verdict"], item["coverage"], item["reason"]))
        print("\n报告：{0}".format(path))
        print("（规则预检不是最终 verdict，正式结论需模型或人工复核）")
        return 0

    if not args.task:
        parser.print_help()
        return 2

    agent = Agent(config=config, offline=args.offline)
    result = agent.run(args.task, verbose=args.verbose)
    print("\n[回答]\n" + result.answer)
    print("\n[运行摘要]")
    for key, value in result.summary():
        print("  {0}: {1}".format(key, value))
    return 0 if result.ok else 1


if __name__ == "__main__":
    sys.exit(main())