# -*- coding: utf-8 -*-
"""
采集 Agent 命令行入口

  python run_cli.py --check
  python run_cli.py --task "搜索 CPAP 依从性的系统综述并抓取前两篇"
  python run_cli.py --task "..." --verbose
  python run_cli.py --task "..." --offline      # 强制离线，验证编排
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

EXPECTED_TOOLS = {"web_search", "web_fetch", "save_file", "read_file", "list_dir"}
BACKEND_APIS = {
    "free": "PubMed / Europe PMC / OpenAlex / Wikipedia（免费，无需 key）",
    "qwen": "千问 enable_search（需 DASHSCOPE_API_KEY，未实测）",
    "both": "两路合并 + 按 URL 去重",
}


def do_check() -> int:
    config = Config()
    agent = Agent(config=config, offline=True)
    print(agent.describe())
    print("检索后端 : {0} -> {1}".format(
        config.search_backend, BACKEND_APIS.get(config.search_backend, "未知后端")))

    names = set(agent.tools.names())
    problems = []
    if names != EXPECTED_TOOLS:
        problems.append("工具集与任务书不一致：多出 {0}，缺少 {1}".format(
            names - EXPECTED_TOOLS, EXPECTED_TOOLS - names))
    for name in names:
        if name not in agent.system_prompt:
            problems.append("提示词里没有提到已注册工具：{0}".format(name))

    files = sorted(config.workspace.glob("*"))
    print("来源目录 : {0}（{1} 个文件）".format(config.workspace, len(files)))
    for path in files[:10]:
        print("           - " + path.name)

    if problems:
        print("\n[FAIL] 发现 {0} 个问题：".format(len(problems)))
        for item in problems:
            print("  - " + item)
        return 1
    print("\n[OK] 自检通过（未联网、未消耗额度）。")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="成人睡眠监测调研 · 采集 Agent")
    parser.add_argument("--check", action="store_true", help="打印自检报告，不联网")
    parser.add_argument("--task", default=None, help="自然语言采集任务")
    parser.add_argument("--offline", action="store_true", help="强制离线假模型")
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