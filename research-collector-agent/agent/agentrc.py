# -*- coding: utf-8 -*-
"""agentrc.py · 采集 Agent 的身份、默认值与离线规则（本 Agent 专有，手写）"""

NAME = "成人睡眠监测调研采集员"

DEFAULTS = {
    "AGENT_MODEL": "qwen-flash",
    "AGENT_TEMPERATURE": "0.2",
    "AGENT_MAX_STEPS": "8",
    "AGENT_MAX_TOKENS": "1500",
    "SEARCH_BACKEND": "free",
}

DIRS = {
    "workspace": "sources",     # 来源卡与抓取原文
    "trace_dir": "traces",
}

OFFLINE_INTRO = (
    "【离线模式】我是采集员。可以试着说："
    "「搜索成人睡眠监测的行业报告」「抓取 https://pubmed.ncbi.nlm.nih.gov/ 的正文」。"
)

# 离线假模型只用来验证编排链路，不代表真实采集质量
OFFLINE_RULES = [
    {"pattern": r"抓取|打开|看看这个?网址|获取正文|https?://", "tool": "web_fetch",
     "args": {"url": "$url"}},
    {"pattern": r"搜索|检索|调研|查找|找一下", "tool": "web_search",
     "args": {"query": "$q", "top_k": 3}},
    {"pattern": r"列目录|有哪些文件", "tool": "list_dir", "args": {"path": "."}},
]