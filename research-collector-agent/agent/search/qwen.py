# -*- coding: utf-8 -*-
"""
search/qwen.py · 千问 enable_search 后端（只做候选 URL 发现）

为什么单独成文件：这条路的返回结构**尚未实测**（本机没有密钥）。
所以代码按最保守方式写：拿不到 search_info 就返回空 + 明确原因，绝不编造结果。

纪律：enable_search 返回的 content 是模型改写过的答案，不是网页原文。
这里只取 search_info.search_results 里的 title/url，正文必须再抓。
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request

ENDPOINT = "https://dashscope.aliyuncs.com/api/v1/services/aigc/text-generation/generation"


def _find_search_info(node):
    """递归找 search_info —— 官方文档没说清它挂在哪一层，就不猜。"""
    if isinstance(node, dict):
        if isinstance(node.get("search_info"), dict):
            return node["search_info"]
        for value in node.values():
            found = _find_search_info(value)
            if found:
                return found
    elif isinstance(node, list):
        for value in node:
            found = _find_search_info(value)
            if found:
                return found
    return None


def search(query, top_k, timeout, api_key="", model="qwen-plus"):
    if not api_key:
        return [], ["qwen: 未配置 DASHSCOPE_API_KEY，已跳过"]

    payload = {
        "model": model,
        "input": {"messages": [{"role": "user", "content": query}]},
        "parameters": {
            "result_format": "message",
            "enable_search": True,
            "search_options": {
                "enable_source": True,       # 关键：要求返回 search_info
                "forced_search": True,       # 别让模型凭记忆答
                "search_strategy": "turbo",  # 最便宜档，够发现候选
            },
        },
    }
    request = urllib.request.Request(
        ENDPOINT,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        method="POST",
        headers={"Authorization": "Bearer " + api_key, "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            data = json.loads(response.read().decode("utf-8", errors="replace"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:200]
        return [], ["qwen: HTTP {0} {1}".format(exc.code, detail)]
    except Exception as exc:                                   # noqa: BLE001
        return [], ["qwen: {0}: {1}".format(type(exc).__name__, str(exc)[:80])]

    info = _find_search_info(data)
    if not info:
        return [], ["qwen: 返回中没有 search_info（可能未开通联网或参数被忽略）"]

    results = info.get("search_results") or []
    items = []
    for record in results[:max(1, int(top_k))]:
        url = (record.get("url") or "").strip()
        if not url:
            continue
        items.append({
            "title": (record.get("title") or "").strip()[:200],
            "url": url,
            "snippet": "来源站点：{0}".format(record.get("site_name", "")),
            "date": "",
            "api": "qwen",
        })
    if not items:
        return [], ["qwen: search_info 里没有可用的 url 字段"]
    return items, None