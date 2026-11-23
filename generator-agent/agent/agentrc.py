# -*- coding: utf-8 -*-
"""agentrc.py · 生成 Agent 的身份、默认值与路径（本 Agent 专有，手写）"""

NAME = "成人睡眠监测调研报告生成员"

DEFAULTS = {
    "AGENT_MODEL": "qwen-plus",      # 出稿需要一定推理
    "AGENT_TEMPERATURE": "0.3",
    "AGENT_MAX_TOKENS": "2500",      # 报告较长
    "AGENT_MAX_STEPS": "8",
}

# 双源强制的两路上游（只读，相对项目根）
EXTRA_DEFAULTS = {
    "KB_FROZEN_DIR": "knowledge-agent/knowledge_base/frozen",
    "KB_REGISTRY": "knowledge-agent/knowledge_base/registry.jsonl",
    "COLLECTOR_SOURCES_DIR": "research-collector-agent/sources",
}

DIRS = {
    "workspace": "reports",          # 只允许往这里写
    "trace_dir": "traces",
}

OFFLINE_INTRO = (
    "【离线模式】我是报告生成员。生成前必须先读固化基线与来源卡。"
    "可以试着说：「生成成人睡眠监测技术现状报告」。"
)

OFFLINE_RULES = [
    {"pattern": r"基线|知识库|检索|查一下", "tool": "search_knowledge",
     "args": {"query": "$q", "top_k": 3}},
    {"pattern": r"来源卡|素材|采集结果", "tool": "load_source_cards", "args": {}},
    {"pattern": r"生成|写|报告|对比表|岗位", "tool": "search_knowledge",
     "args": {"query": "$q", "top_k": 3}},
]