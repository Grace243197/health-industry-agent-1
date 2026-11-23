# -*- coding: utf-8 -*-
"""
sync_core.py · 把 shared-core 同步到各 Agent 目录

为什么需要它：
  任务书要求每个 Agent 目录自包含（能单独拷走运行），但公共内核只有一份真源。
  手改五份副本必然漂移，所以用生成 + 指纹校验来兜住。

用法：
  python tools/sync_core.py                 # 同步所有带 agent/agentrc.py 的目录
  python tools/sync_core.py --check         # 只检查是否与模板一致（CI/自检用）
  python tools/sync_core.py --target verify-agent

约定：
  生成文件头部会写 AUTO-GENERATED 与 CORE_VERSION；改内核请改 shared-core/，
  不要直接改各 Agent 目录里的 config.py / model.py / core.py / memory.py /
  toolkit.py / prompts_base.py。
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TEMPLATE = ROOT / "shared-core"
CORE_VERSION = "20261123.5"

# shared-core 里哪些文件要分发；不在列表里的（如 README）只留模板
GENERATED = [
    "config.py", "model.py", "core.py", "memory.py", "toolkit.py", "prompts_base.py",
]

INIT_CONTENT = '''# AUTO-GENERATED from shared-core by tools/sync_core.py — DO NOT EDIT
# CORE_VERSION: {version}
from .core import Agent, Result  # noqa: F401
from .config import Config  # noqa: F401
'''


def with_header(text: str, source: str) -> str:
    """在保持 PEP 263 编码声明有效的前提下插入生成标记。"""
    lines = text.splitlines(keepends=True)
    insert_at = 1 if lines and lines[0].startswith("# -*- coding") else 0
    header = [
        "# AUTO-GENERATED from shared-core/{0} by tools/sync_core.py — DO NOT EDIT\n".format(source),
        "# CORE_VERSION: {0}\n".format(CORE_VERSION),
    ]
    return "".join(lines[:insert_at] + header + lines[insert_at:])


def discover_targets() -> list[Path]:
    """找出仓库根目录下所有带 agent/agentrc.py 的 Agent 目录。"""
    targets = []
    for candidate in sorted(ROOT.iterdir()):
        if not candidate.is_dir() or candidate == TEMPLATE:
            continue
        if (candidate / "agent" / "agentrc.py").is_file():
            targets.append(candidate)
    return targets


def expected_files() -> dict:
    expected = {}
    for name in GENERATED:
        source = TEMPLATE / name
        if not source.is_file():
            raise SystemExit("模板缺失：{0}".format(source))
        expected[name] = with_header(source.read_text(encoding="utf-8"), name)
    expected["__init__.py"] = INIT_CONTENT.format(version=CORE_VERSION)
    return expected


def sync_one(target: Path, expected: dict, check: bool) -> list[str]:
    problems = []
    agent_dir = target / "agent"
    agent_dir.mkdir(parents=True, exist_ok=True)

    for name, content in expected.items():
        path = agent_dir / name
        if check:
            if not path.is_file():
                problems.append("{0}/{1} 缺失".format(target.name, name))
            elif path.read_text(encoding="utf-8") != content:
                problems.append("{0}/{1} 与模板不一致（需运行 sync_core.py）".format(
                    target.name, name))
            continue
        path.write_text(content, encoding="utf-8")

    if check and not problems:
        print("[OK] {0} 内核版本 {1}".format(target.name, CORE_VERSION))
    elif not check:
        print("[SYNC] {0} <- {1} 个文件".format(target.name, len(expected)))
    return problems


def main() -> int:
    ap = argparse.ArgumentParser(description="同步 shared-core 到各 Agent 目录")
    ap.add_argument("--check", action="store_true", help="只校验，不写入")
    ap.add_argument("--target", action="append", default=None,
                    help="只处理指定目录（可重复），默认自动发现")
    args = ap.parse_args()

    targets = [ROOT / name for name in args.target] if args.target else discover_targets()
    if not targets:
        print("没有找到任何带 agent/agentrc.py 的 Agent 目录。")
        return 1

    expected = expected_files()
    problems = []
    for target in targets:
        if not target.is_dir():
            problems.append("目标不存在：{0}".format(target))
            continue
        problems.extend(sync_one(target, expected, args.check))

    if problems:
        print("\n发现 {0} 处问题：".format(len(problems)))
        for item in problems:
            print("  - " + item)
        return 1

    print("\n内核版本 {0}；目标 {1} 个。".format(CORE_VERSION, len(targets)))
    return 0


if __name__ == "__main__":
    sys.exit(main())