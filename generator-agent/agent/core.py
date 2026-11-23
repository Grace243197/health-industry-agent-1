# -*- coding: utf-8 -*-
# AUTO-GENERATED from shared-core/core.py by tools/sync_core.py — DO NOT EDIT
# CORE_VERSION: 20261123.5
"""
core.py · ReAct 主循环（由 shared-core 同步生成，请勿手改）

Agent = 模型 + 工具 + 一个让它自己决定下一步的循环。
本文件只约定了"怎么循环"，具体是谁、有什么工具、规则是什么，全在
各 Agent 目录的 agentrc.py / tools.py / prompts.py 里。

三道保险：步数上限、重复调用拦截、工具异常回灌给模型。
"""

from __future__ import annotations

import datetime
import json
import os
import re
import time

from .config import Config
from .model import Model, ModelError
from .toolkit import Sandbox


class Result(object):
    def __init__(self, task):
        self.task = task
        self.answer = ""
        self.status = "unknown"      # completed / max_steps / error / empty
        self.steps = []
        self.tool_calls = []
        self.model_requests = 0
        self.total_tokens = 0
        self.elapsed = 0.0
        self.error = None
        self.trace_path = None

    @property
    def ok(self):
        return self.status == "completed"

    def summary(self):
        return [
            ("任务", self.task[:60]),
            ("状态", self.status),
            ("耗时", "{0} 秒".format(self.elapsed)),
            ("模型请求", self.model_requests),
            ("工具调用", len(self.tool_calls)),
            ("工具序列", " → ".join(c["name"] for c in self.tool_calls) or "无"),
            ("Token", self.total_tokens),
            ("轨迹", self.trace_path or "(未保存)"),
        ]

    def to_dict(self):
        data = dict(self.summary())
        data.update({"answer": self.answer, "steps": self.steps,
                     "tool_calls": self.tool_calls, "error": self.error})
        return data


class Agent(object):
    def __init__(self, config=None, offline=False, on_event=None):
        from . import prompts as agent_prompts, tools as agent_tools

        self.config = config or Config()
        self.sandbox = Sandbox(self.config.workspace)
        self.tools = agent_tools.build(self.config, self.sandbox)
        self.system_prompt = agent_prompts.build(self.config, set(self.tools.names()))
        self.model = Model(self.config, offline=offline)
        self.on_event = on_event

    def new_session(self):
        from .memory import ShortTermMemory
        return ShortTermMemory(self.system_prompt, self.config.context_budget)

    def run(self, task, session=None, verbose=False):
        result = Result(task)
        started = time.time()
        if session is None:
            session = self.new_session()
        session.add_user(task)

        seen = set()
        self._emit("task_start", {"task": task}, verbose)
        try:
            for step in range(1, self.config.max_steps + 1):
                messages = session.messages()
                reply, usage = self.model.chat(messages, tools=self.tools.schemas())
                result.model_requests += 1
                result.total_tokens += usage.get("total_tokens", 0)
                session.add(reply)

                tool_calls = reply.get("tool_calls") or []
                if not tool_calls:
                    result.answer = (reply.get("content") or "").strip()
                    result.steps.append({"step": step, "type": "answer",
                                         "tokens": usage.get("total_tokens", 0)})
                    result.status = "completed" if result.answer else "empty"
                    self._emit("answer", {"step": step, "answer": result.answer}, verbose)
                    break

                record = {"step": step, "type": "tools", "calls": [],
                          "tokens": usage.get("total_tokens", 0)}
                for call in tool_calls:
                    function = call.get("function") or {}
                    tool_name = function.get("name", "")
                    arguments = function.get("arguments") or "{}"
                    signature = (tool_name, arguments)

                    if signature in seen:
                        output = ("错误：同样的工具与参数刚调用过，结果不会变。"
                                  "请换思路或直接说明困难。")
                        self._emit("blocked", {"name": tool_name}, verbose)
                    else:
                        seen.add(signature)
                        output = self.tools.call(tool_name, arguments)

                    record["calls"].append({"name": tool_name, "arguments": arguments,
                                            "result": output[:800]})
                    result.tool_calls.append({"step": step, "name": tool_name,
                                              "arguments": arguments, "result": output[:800]})
                    session.add({"role": "tool", "tool_call_id": call.get("id"),
                                 "content": output})
                    self._emit("tool", {"step": step, "name": tool_name,
                                        "arguments": arguments, "result": output[:300]}, verbose)

                result.steps.append(record)

                # 可选扩展点：调度 Agent 用它实现"校验驳回后自动回退一次"。
                # 返回 True 表示 hook 已往会话里追加了新指令，应继续循环而不是结束。
                from . import agentrc
                hook = getattr(agentrc, "after_tools", None)
                if hook is not None:
                    try:
                        if hook(self, result, session):
                            self._emit("rollback", {"step": step}, verbose)
                            continue
                    except Exception as exc:                   # noqa: BLE001
                        self._emit("rollback_error", {"error": str(exc)}, verbose)
            else:
                result.status = "max_steps"
                result.answer = "未在 {0} 步内完成，已中止。工具序列：{1}".format(
                    self.config.max_steps,
                    " → ".join(c["name"] for c in result.tool_calls) or "无")
                self._emit("max_steps", {"limit": self.config.max_steps}, verbose)

        except ModelError as exc:
            result.status = "error"
            result.error = str(exc)
            result.answer = "模型调用失败：{0}".format(exc)
            self._emit("error", {"error": str(exc)}, verbose)
        except Exception as exc:                                # noqa: BLE001
            result.status = "error"
            result.error = "{0}: {1}".format(type(exc).__name__, exc)
            result.answer = "执行异常：{0}".format(result.error)
            self._emit("error", {"error": result.error}, verbose)

        result.elapsed = round(time.time() - started, 2)
        if self.config.save_trace:
            result.trace_path = self._save_trace(result)
        self._emit("task_end", dict(result.summary()), verbose)
        return result

    def _emit(self, kind, payload, verbose=False):
        event = dict(payload)
        event["kind"] = kind
        event["time"] = datetime.datetime.now().strftime("%H:%M:%S")
        if self.on_event:
            try:
                self.on_event(event)
            except Exception:                                  # noqa: BLE001
                pass
        if verbose:
            print("[{0}] {1}".format(kind, {
                k: v for k, v in event.items() if k not in ("kind", "time")}))

    def _save_trace(self, result):
        os.makedirs(self.config.trace_dir, exist_ok=True)
        stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
        slug = re.sub(r"[^\w\u4e00-\u9fff]+", "-", result.task)[:24].strip("-") or "task"
        path = self.config.trace_dir / "{0}-{1}.json".format(stamp, slug)
        payload = {"config": self.config.public_snapshot(), "result": result.to_dict()}
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return str(path)

    def describe(self):
        return "\n".join([
            "======== Agent 自检 ========",
            self.config.describe(),
            "工具数量 : {0}".format(len(self.tools.names())),
            "工具清单 : {0}".format(", ".join(self.tools.names())),
            "沙箱目录 : {0}".format(self.sandbox.root),
            "提示词长度 : {0} 字符".format(len(self.system_prompt)),
        ])

    def tool_manifest(self):
        return self.tools.describe()