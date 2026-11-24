# -*- coding: utf-8 -*-
"""agentrc.py · 知识库管家的身份、默认值与路径（本 Agent 专有，手写）"""

NAME = "成人睡眠监测调研知识库管家"

DEFAULTS = {
    "AGENT_MODEL": "qwen-plus",      # 管理 + 判级需要一定判断力
    "AGENT_TEMPERATURE": "0.2",
    "AGENT_MAX_STEPS": "8",
}

EXTRA_DEFAULTS = {
    "COLLECTOR_SOURCES_DIR": "research-collector-agent/sources",
    "KB_DIR": "knowledge_base",
}

DIRS = {
    "workspace": "knowledge_base",   # 沙箱根 = knowledge_base/
    "trace_dir": "traces",
}

OFFLINE_INTRO = (
    "【离线模式】我是知识库管家。可以试着说："
    "「预处理 research-collector-agent/sources/SRC001.md」「列出所有来源」"
    "「把 SRC001 冻结进基线库，批准人：张三」。"
)

OFFLINE_RULES = [
    {"pattern": r"预处理|入库|标准化", "tool": "preprocess_doc", "args": {"path": "$path"}},
    {"pattern": r"冻结|批准", "tool": "freeze_source",
     "args": {"source_id": "$sid", "approved_by": "$approver"}},
    {"pattern": r"归档", "tool": "archive_source", "args": {"source_id": "$sid"}},
    {"pattern": r"列出|有哪些|清单", "tool": "list_sources", "args": {}},
    {"pattern": r"检索|查|找", "tool": "search_knowledge", "args": {"query": "$q", "top_k": 3}},
]