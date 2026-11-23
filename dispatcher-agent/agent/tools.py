# -*- coding: utf-8 -*-
"""
tools.py · 总调度的六个能力（本 Agent 专有，手写）

四个 run_* 用 subprocess 调下游 run_cli.py，超时/非零退出都如实回报；
list_agents 用于自检；read_file / list_dir 只读各 Agent 的产出目录。

调度不直接改下游文件，也不替下游下结论。
"""

from __future__ import annotations

import datetime
import json
import os
import subprocess
import sys

from .toolkit import ToolRegistry

READ_PREFIXES = (
    "research-collector-agent/sources",
    "generator-agent/reports",
    "verify-agent/verifications",
    "knowledge-agent/knowledge_base",
    "runs",
    "output",
)


def _audit(config, agent_name, task, ok, returncode, summary):
    audit_dir = config.extra_dirs.get("audit")
    if audit_dir is None:
        return
    record = {
        "time": datetime.datetime.now().isoformat(timespec="seconds"),
        "target": agent_name,
        "task": task,
        "ok": ok,
        "returncode": returncode,
        "summary": summary[:300],
    }
    with open(audit_dir / "audit_log.jsonl", "a", encoding="utf-8") as file:
        file.write(json.dumps(record, ensure_ascii=False) + "\n")


def _dispatch(config, agent_name, path, task, extra_args=()):
    """调用下游 Agent。永远返回文本，不抛异常。"""
    if not path.is_file():
        _audit(config, agent_name, task, False, None, "入口不存在")
        return ("调用失败：下游入口不存在 {0}。\n"
                "（该 Agent 尚未实现，不能伪造它的产出。）").format(path)

    command = [sys.executable, str(path), "--task", task, *extra_args]
    # 关键：Windows 下子进程默认按 GBK 写管道，父进程按 UTF-8 读会全是乱码，
    # 连"驳回"两个字都识别不出来。强制子进程输出 UTF-8。
    env = dict(os.environ)
    env["PYTHONIOENCODING"] = "utf-8"
    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=config.timeout,
            cwd=str(config.project_root),
            env=env,
        )
    except subprocess.TimeoutExpired:
        _audit(config, agent_name, task, False, None, "下游超时")
        return "调用失败：{0} 超时（>{1} 秒），已中止。".format(agent_name, config.timeout)
    except OSError as exc:
        _audit(config, agent_name, task, False, None, str(exc))
        return "调用失败：{0} 无法启动（{1}）。".format(agent_name, exc)

    stdout = (completed.stdout or "").strip()
    stderr = (completed.stderr or "").strip()
    ok = completed.returncode == 0
    _audit(config, agent_name, task, ok, completed.returncode,
           (stdout or stderr)[:300])

    if not ok:
        return ("调用失败：{0} 返回码 {1}。\n标准错误摘要：{2}\n标准输出摘要：{3}").format(
            agent_name, completed.returncode, stderr[:600] or "(空)", stdout[:600] or "(空)")

    return "调用成功：{0}（返回码 0）\n{1}".format(agent_name, stdout[:4000] or "(下游没有输出)")


def build(config, sandbox):
    registry = ToolRegistry()

    def _path(key, default):
        return config.project_path(key, default)

    @registry.register
    def run_collector(task):
        """把采集任务交给「调研采集 Agent」，返回它的输出摘要。

        用户要搜/查/调研/抓素材时用这个。不要自己去编素材。

        Args:
            task: 交给下游的自然语言任务，例如 "搜索 CPAP 依从性研究并保存来源卡"
        """
        return _dispatch(config, "采集 Agent",
                         _path("COLLECTOR_RUN_CLI", "research-collector-agent/run_cli.py"), task)

    @registry.register
    def run_knowledge(task):
        """把入库/检索/冻结任务交给「知识库 Agent」。

        Args:
            task: 例如 "把 sources 里的来源卡预处理入 staging"
        """
        return _dispatch(config, "知识库 Agent",
                         _path("KNOWLEDGE_RUN_CLI", "knowledge-agent/run_cli.py"), task)

    @registry.register
    def run_generator(task):
        """把出稿任务交给「生成 Agent」，返回报告落盘路径摘要。

        Args:
            task: 例如 "生成成人睡眠监测技术现状报告"
        """
        return _dispatch(config, "生成 Agent",
                         _path("GENERATOR_RUN_CLI", "generator-agent/run_cli.py"), task)

    @registry.register
    def run_verifier(task):
        """把初稿交给「证据校验 Agent」审计；输出里会带 verdict=rejected 或 verdict=passed。

        校验驳回时不要自己改结论，按规则回退一次。

        Args:
            task: 例如 "校验 reports/latest.md 里的结论"
        """
        path = _path("VERIFIER_RUN_CLI", "verify-agent/run_cli.py")
        output = _dispatch(config, "校验 Agent", path, task)
        if "调用失败" in output:
            return output

        lowered = output.lower()
        rejected = any(marker in output for marker in ("驳回", "不通过", "需回退")) \
            or "verdict: contradicted" in lowered
        verdict = "rejected" if rejected else "passed"
        return "{0}\nverdict={1}".format(output, verdict)

    @registry.register
    def list_agents():
        """列出四个下游 Agent 的入口路径与是否存在（自检/路由前确认用）。"""
        rows = ["下游 Agent 状态："]
        for label, key, default in (
            ("采集", "COLLECTOR_RUN_CLI", "research-collector-agent/run_cli.py"),
            ("知识库", "KNOWLEDGE_RUN_CLI", "knowledge-agent/run_cli.py"),
            ("生成", "GENERATOR_RUN_CLI", "generator-agent/run_cli.py"),
            ("校验", "VERIFIER_RUN_CLI", "verify-agent/run_cli.py"),
        ):
            path = _path(key, default)
            rows.append("- {0}：{1} {2}".format(
                label, path, "存在" if path.is_file() else "缺失"))
        return "\n".join(rows)

    def _require_readable(relative):
        normalized = os.path.normpath(relative).replace(os.sep, "/")
        if not any(normalized == p or normalized.startswith(p + "/") for p in READ_PREFIXES):
            raise PermissionError("调度只能读下游产出目录，收到：{0}".format(relative))
        return config.project_root / normalized

    @registry.register
    def read_file(path):
        """只读下游产出（来源卡、报告、校验报告等），用于汇总。

        Args:
            path: 相对项目根的路径，必须位于 sources/reports/verifications/knowledge_base 下
        """
        target = _require_readable(path)
        if not target.is_file():
            raise FileNotFoundError("文件不存在：{0}".format(path))
        return target.read_text(encoding="utf-8", errors="replace")

    @registry.register
    def list_dir(path="."):
        """列出下游产出目录（只读）。

        Args:
            path: 相对项目根的目录，例如 "generator-agent/reports"
        """
        target = config.project_root / path
        if not target.is_dir():
            raise NotADirectoryError("不是目录：{0}".format(path))
        rows = []
        for name in sorted(os.listdir(target)):
            full = target / name
            rows.append("[目录] " + name if full.is_dir()
                        else "[文件] {0} ({1} 字节)".format(name, full.stat().st_size))
        return "\n".join(rows) if rows else "(空目录)"

    return registry