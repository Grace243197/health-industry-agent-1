#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""采集 Agent 的快速自检（不需要 key，不联网）。"""

import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent


def main() -> int:
    commands = [
        [sys.executable, "run_cli.py", "--check"],
        [sys.executable, "run_cli.py", "--task", "搜索睡眠监测的行业概况", "--offline"],
    ]
    for command in commands:
        print("\n$ " + " ".join(command))
        completed = subprocess.run(command, cwd=HERE)
        if completed.returncode != 0:
            return completed.returncode
    return 0


if __name__ == "__main__":
    sys.exit(main())