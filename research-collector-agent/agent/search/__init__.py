# -*- coding: utf-8 -*-
"""
search/__init__.py · 采集检索后端路由

三个可选后端，用 SEARCH_BACKEND 切换：
  free  —— 免费学术/百科 API（PubMed、Europe PMC、OpenAlex、Wikipedia），零 key、零费用
  qwen  —— 千问 enable_search（DashScope 原生协议），只用来发现候选 URL
  both  —— 两路合并按 URL 去重，便于以后做 A/B 对比

纪律：所有后端返回的都只是"候选线索"，正文必须再走 web_fetch 抓取核实。
"""

from __future__ import annotations

from . import free, qwen


def run(query, top_k, backend, timeout, api_key="", model="qwen-plus"):
    backend = (backend or "free").lower()
    results, errors = [], []

    if backend in ("free", "both"):
        items, errs = free.search(query, top_k, timeout)
        results.extend(items)
        errors.extend(errs)

    if backend in ("qwen", "both"):
        items, errs = qwen.search(query, top_k, timeout, api_key=api_key, model=model)
        results.extend(items)
        errors.extend(errs)

    # 按 URL 去重，先到先得（free 在前，便于比较两边覆盖差异）
    seen, merged = set(), []
    for item in results:
        url = (item.get("url") or "").strip()
        if not url or url in seen:
            continue
        seen.add(url)
        merged.append(item)

    return merged[:max(1, int(top_k)) * 2], errors