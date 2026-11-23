# -*- coding: utf-8 -*-
"""
model.py · 模型客户端（由 shared-core 同步生成，请勿手改）

只做三件事：发请求、指数退避重试、记账。
没配密钥时走离线假模型，让整条编排链路在零成本下也能验证。
"""

from __future__ import annotations

import json
import re
import time

import requests


class ModelError(Exception):
    """模型服务不可用（密钥错、网络断、限流耗尽）。"""


class Model(object):
    def __init__(self, config, offline=False):
        self.config = config
        self.offline = offline
        self.request_count = 0
        self.total_tokens = 0

    def chat(self, messages, tools=None):
        if self.offline or not self.config.online:
            from . import agentrc
            return offline_model(messages, tools,
                                 getattr(agentrc, "OFFLINE_RULES", []),
                                 getattr(agentrc, "OFFLINE_INTRO", ""))

        payload = {
            "model": self.config.model,
            "messages": messages,
            "temperature": self.config.temperature,
            "max_tokens": self.config.max_tokens,
        }
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"
        if self.config.enable_thinking is not None:
            payload["enable_thinking"] = self.config.enable_thinking

        data = self._post_with_retry(payload)
        choices = data.get("choices") or []
        if not choices:
            raise ModelError("接口没有返回 choices：" + json.dumps(data, ensure_ascii=False)[:300])

        message = {k: v for k, v in (choices[0].get("message") or {}).items()
                   if k in ("role", "content", "tool_calls", "name")}
        message.setdefault("role", "assistant")

        usage = data.get("usage") or {}
        self.request_count += 1
        self.total_tokens += usage.get("total_tokens", 0)
        return message, usage

    def _post_with_retry(self, payload):
        url = self.config.base_url.rstrip("/") + "/chat/completions"
        headers = {"Authorization": "Bearer " + self.config.api_key,
                   "Content-Type": "application/json"}
        last_error = "未知错误"

        for attempt in range(self.config.max_retries + 1):
            try:
                response = requests.post(url, headers=headers, json=payload,
                                         timeout=self.config.timeout)
            except requests.RequestException as exc:
                last_error = "网络异常 {0}: {1}".format(type(exc).__name__, exc)
            else:
                if response.status_code == 200:
                    return response.json()
                detail = "HTTP {0}: {1}".format(response.status_code, response.text[:200])
                if response.status_code == 429 or response.status_code >= 500:
                    last_error = detail
                else:
                    raise ModelError(detail)

            if attempt < self.config.max_retries:
                time.sleep(2 ** attempt)

        raise ModelError("重试 {0} 次后仍失败 —— {1}".format(self.config.max_retries, last_error))


# ============================================================ 离线假模型
_TASK_VERBS = re.compile(
    r"^(?:请|帮我|麻烦你?|给我)?\s*"
    r"(?:搜索|搜一下|搜|检索|调研|查找|查一下|查|找一下|找|生成|写一份|写|校验|核对|复核|入库|预处理)"
    r"\s*"
)


def _clean(text: str) -> str:
    """把「调研成人睡眠监测行业」这类任务句压成检索词「成人睡眠监测行业」。"""
    text = _TASK_VERBS.sub("", text or "")
    return re.sub(r"[？?。！!，,、\s]+", " ", text).strip()


def _fill_arguments(arguments: dict, user_text: str) -> dict:
    """把 $q / $url / $path 占位符替换成用户输入里能取到的值。"""
    url_match = re.search(r"https?://[^\s，。；]+", user_text)
    url = url_match.group() if url_match else ""
    path_match = re.search(r"[\w\-./]+\.(?:md|txt|json)", user_text)
    path = path_match.group() if path_match else ""

    filled = {}
    for key, value in arguments.items():
        if value == "$q":
            filled[key] = _clean(user_text)[:40]
        elif value == "$task":
            # 原句透传给下游：下游要靠"调研/生成/校验"这些动词判断该做什么，
            # 不能像检索词那样把动词剥掉。
            filled[key] = (user_text or "").strip()[:200]
        elif value == "$url":
            filled[key] = url
        elif value == "$path":
            filled[key] = path
        else:
            filled[key] = value
    return filled


def offline_model(messages, tools, rules, intro):
    """关键词触发的假模型：只验证编排，不产生任何真实结论。"""
    usage = {"prompt_tokens": 60, "completion_tokens": 20, "total_tokens": 80}
    available = {t["function"]["name"] for t in (tools or [])}

    last_user = ""
    for item in reversed(messages):
        if item.get("role") == "user":
            last_user = item.get("content") or ""
            break

    tool_results = [m for m in messages if m.get("role") == "tool"]
    if tool_results:
        evidence = "\n".join(str(t.get("content"))[:240] for t in tool_results[-3:])
        return {"role": "assistant", "content":
                "【离线模式】工具已返回，摘录如下（未做任何推断）：\n\n{0}".format(evidence)}, usage

    tried = len([m for m in messages if m.get("role") == "assistant"]) + 1
    for rule in rules:
        if rule["tool"] not in available:
            continue
        if re.search(rule["pattern"], last_user):
            arguments = _fill_arguments(rule.get("args", {}), last_user)
            if any(v == "" for v in arguments.values()):
                continue
            return {"role": "assistant", "content": "", "tool_calls": [{
                "id": "offline_{0}".format(tried),
                "type": "function",
                "function": {"name": rule["tool"],
                             "arguments": json.dumps(arguments, ensure_ascii=False)},
            }]}, usage

    return {"role": "assistant", "content": intro or "【离线模式】没有匹配到可执行的工具。"}, usage