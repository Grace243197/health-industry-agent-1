# -*- coding: utf-8 -*-
# AUTO-GENERATED from shared-core/memory.py by tools/sync_core.py — DO NOT EDIT
# CORE_VERSION: 20261123.1
"""
memory.py · 会话内记忆（由 shared-core 同步生成，请勿手改）

只保留短期记忆：把对话历史裁到预算内，并修掉会让接口报错的孤儿消息。
跨会话的长期记忆这五个 Agent 都不需要，所以不实现。
"""

from __future__ import annotations


class ShortTermMemory(object):
    def __init__(self, system_prompt, budget_chars=24000):
        self.system_prompt = system_prompt
        self.budget = int(budget_chars)
        self._messages = []

    def add_user(self, content):
        self._messages.append({"role": "user", "content": content})

    def add(self, message):
        self._messages.append(message)

    def clear(self):
        self._messages = []

    def __len__(self):
        return len(self._messages)

    def messages(self):
        """返回 system + 裁剪后的历史。"""
        trimmed = self._trim(self._messages)
        return [{"role": "system", "content": self.system_prompt}] + self._repair(trimmed)

    def _trim(self, messages):
        total = sum(len(str(m.get("content") or "")) for m in messages)
        if total <= self.budget:
            return list(messages)

        # 从旧到新丢，但保证 tool 结果和它对应的 assistant.tool_calls 一起丢
        kept, running = [], 0
        for message in reversed(messages):
            size = len(str(message.get("content") or ""))
            if running + size > self.budget:
                break
            kept.append(message)
            running += size
        kept.reverse()
        note = {"role": "user", "content":
                "（已省略更早的 {0} 条消息以控制上下文长度）".format(len(messages) - len(kept))}
        return [note] + kept

    @staticmethod
    def _repair(messages):
        """孤儿 tool 消息、以及没有结果的 tool_calls，都会被接口拒绝，必须清理。"""
        tool_by_id = {m.get("tool_call_id"): m for m in messages if m.get("role") == "tool"}
        repaired = []
        for message in messages:
            role = message.get("role")
            if role == "tool":
                continue                      # 统一在下方紧跟 assistant 插入
            if role == "assistant" and message.get("tool_calls"):
                ids = [call.get("id") for call in message["tool_calls"]]
                if not any(call_id in tool_by_id for call_id in ids):
                    continue                  # 一个结果都没有，整条声明作废
                repaired.append(message)
                for call_id in ids:
                    if call_id in tool_by_id:
                        repaired.append(tool_by_id[call_id])
                continue
            repaired.append(message)
        return repaired