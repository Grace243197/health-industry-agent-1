# -*- coding: utf-8 -*-
"""agentrc.py · 总调度的身份、下游路径与回退钩子（本 Agent 专有，手写）"""

NAME = "成人睡眠监测调研总调度"

DEFAULTS = {
    "AGENT_MODEL": "qwen-plus",      # 路由要稳，工具调用要准
    "AGENT_MAX_STEPS": "10",         # 含回退
    "AGENT_TIMEOUT": "180",          # 比下游自身超时更宽松
    "AGENT_TEMPERATURE": "0.2",
}

EXTRA_DEFAULTS = {
    "COLLECTOR_RUN_CLI": "research-collector-agent/run_cli.py",
    "KNOWLEDGE_RUN_CLI": "knowledge-agent/run_cli.py",
    "GENERATOR_RUN_CLI": "generator-agent/run_cli.py",
    "VERIFIER_RUN_CLI": "verify-agent/run_cli.py",
}

DIRS = {
    "workspace": ".",
    "trace_dir": "traces",
    "audit": "audit",
}

OFFLINE_INTRO = (
    "【离线模式】我是总调度，只负责分发与汇总。"
    "可以试着说：「调研成人睡眠监测行业」「校验上一版报告」「生成一份报告」。"
)

OFFLINE_RULES = [
    {"pattern": r"采集|调研|搜|抓", "tool": "run_collector", "args": {"task": "$task"}},
    {"pattern": r"入库|知识库|预处理", "tool": "run_knowledge", "args": {"task": "$task"}},
    {"pattern": r"生成|写报告|对比表|岗位", "tool": "run_generator", "args": {"task": "$task"}},
    {"pattern": r"校验|核对|复核|质疑", "tool": "run_verifier", "args": {"task": "$task"}},
    {"pattern": r"有哪些|列出|状态", "tool": "list_agents", "args": {}},
]


def after_tools(agent, result, session):
    """校验驳回时自动回退一次；再驳回就停，把疑点原样交还用户。

    返回 True 表示已追加新指令，主循环应继续；返回 False 表示不干预。
    """
    if getattr(result, "rolled_back", False):
        return False
    rejected = any("verdict=rejected" in call.get("result", "")
                   for call in result.tool_calls)
    if not rejected:
        return False

    result.rolled_back = True
    session.add_user(
        "【调度指令】上一轮校验驳回了。现在回退一次：先让生成 Agent 依据疑点清单重写，"
        "再交校验 Agent 复核。若这次仍驳回，就停止回退，把疑点清单原样写进最终汇总，"
        "不得自行修改结论。"
    )
    return True