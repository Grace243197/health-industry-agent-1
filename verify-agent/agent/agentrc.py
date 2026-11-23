# -*- coding: utf-8 -*-
"""agentrc.py · 校验 Agent 的身份、默认值与离线规则（本 Agent 专有，手写）"""

NAME = "成人睡眠监测调研证据校验官"

DEFAULTS = {
    "AGENT_MODEL": "qwen-plus",      # 逐字比对需要更稳的推理
    "AGENT_TEMPERATURE": "0.1",      # 越低越稳
    "AGENT_MAX_STEPS": "6",
    "AGENT_ENABLE_THINKING": "false",
}

DIRS = {
    "workspace": ".",                # 沙箱根 = 本目录，读 sources/ 与 claims/
    "trace_dir": "traces",
    "sources": "sources",
    "claims": "claims",
    "verifications": "verifications",
}

OFFLINE_INTRO = (
    "【离线模式】我是证据校验官，默认质疑。"
    "可以试着说：「列出待校验的 claim」「在 sources 里搜 PSG 的原文」。"
)

OFFLINE_RULES = [
    {"pattern": r"列出|清单|有哪些", "tool": "list_dir", "args": {"path": "claims"}},
    {"pattern": r"搜|核对|找原文|逐字", "tool": "grep_source", "args": {"pattern": "$q"}},
]