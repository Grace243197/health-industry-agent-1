# -*- coding: utf-8 -*-
# AUTO-GENERATED from shared-core/config.py by tools/sync_core.py — DO NOT EDIT
# CORE_VERSION: 20261123.5
"""
config.py · 公共内核配置（由 shared-core 同步生成，请勿手改）

优先级：环境变量 > .env 文件 > agentrc.DEFAULTS > 代码兜底。
每个 Agent 的默认模型、步数、目录在各自的 agent/agentrc.py 里声明。
"""

from __future__ import annotations

import os
from pathlib import Path


def read_env_file(path: Path) -> dict:
    """极简 .env 解析：一行一个 KEY=VALUE，忽略注释与空行。"""
    values = {}
    if not path.is_file():
        return values
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


FLAGS = ("1", "true", "yes", "on")


class Config(object):
    FILE_SETTINGS = (
        "AGENT_API_KEY", "AGENT_BASE_URL", "AGENT_MODEL",
        "AGENT_TEMPERATURE", "AGENT_MAX_TOKENS", "AGENT_TIMEOUT",
        "AGENT_MAX_RETRIES", "AGENT_MAX_STEPS", "AGENT_CONTEXT_BUDGET",
        "AGENT_ENABLE_THINKING", "AGENT_SAVE_TRACE",
        "SEARCH_BACKEND", "SEARCH_TIMEOUT", "DASHSCOPE_API_KEY",
    )

    def __init__(self, base_dir=None, **overrides):
        from . import agentrc

        self.base_dir = Path(base_dir or Path(__file__).resolve().parent.parent)
        self.name = getattr(agentrc, "NAME", "未命名 Agent")

        merged = {}
        merged.update(getattr(agentrc, "DEFAULTS", {}))
        merged.update(getattr(agentrc, "EXTRA_DEFAULTS", {}))
        merged.update(read_env_file(self.base_dir / ".env"))
        merged.update({k: v for k, v in os.environ.items() if v})
        merged.update({k: str(v) for k, v in overrides.items() if v is not None})

        def get(key, default=""):
            value = merged.get(key, default)
            return default if value is None or str(value).strip() == "" else str(value).strip()

        self.api_key = get("AGENT_API_KEY") or get("DASHSCOPE_API_KEY")
        self.base_url = get("AGENT_BASE_URL",
                            "https://dashscope.aliyuncs.com/compatible-mode/v1")
        self.model = get("AGENT_MODEL", "qwen-plus")
        self.temperature = float(get("AGENT_TEMPERATURE", "0.2"))
        self.max_tokens = int(get("AGENT_MAX_TOKENS", "1500"))
        self.timeout = int(get("AGENT_TIMEOUT", "120"))
        self.max_retries = int(get("AGENT_MAX_RETRIES", "2"))
        self.max_steps = int(get("AGENT_MAX_STEPS", "8"))
        self.context_budget = int(get("AGENT_CONTEXT_BUDGET", "24000"))
        self.save_trace = get("AGENT_SAVE_TRACE", "true").lower() in FLAGS

        raw_thinking = merged.get("AGENT_ENABLE_THINKING")
        self.enable_thinking = None
        if raw_thinking is not None and str(raw_thinking).strip() != "":
            self.enable_thinking = str(raw_thinking).strip().lower() in FLAGS

        self.search_backend = get("SEARCH_BACKEND", "free").lower()
        self.search_timeout = int(get("SEARCH_TIMEOUT", "25"))

        # 保留合并后的原始配置，供各 Agent 读取自己的专属路径项（如 KB_FROZEN_DIR）
        self.settings = merged
        # 上游/下游路径按"项目根"解析，而不是按本 Agent 目录
        self.project_root = self.base_dir.parent

        dirs = getattr(agentrc, "DIRS", {})
        self.workspace = self.base_dir / dirs.get("workspace", "workspace")
        self.trace_dir = self.base_dir / dirs.get("trace_dir", "traces")
        self.extra_dirs = {
            key: self.base_dir / value for key, value in dirs.items()
            if key not in ("workspace", "trace_dir")
        }
        for path in [self.workspace, self.trace_dir, *self.extra_dirs.values()]:
            path.mkdir(parents=True, exist_ok=True)

    def project_path(self, key: str, default: str = "") -> Path:
        """取一个相对项目根的路径（用于上游/下游目录，如 research-collector-agent/sources）。"""
        value = str(self.settings.get(key) or default)
        path = Path(value)
        return path if path.is_absolute() else self.project_root / path

    # ------------------------------------------------------------ 展示
    @property
    def online(self) -> bool:
        return bool(self.api_key)

    def masked_key(self) -> str:
        if not self.api_key:
            return "(未配置)"
        if len(self.api_key) <= 12:
            return "*" * len(self.api_key)
        return self.api_key[:6] + "*" * 8 + self.api_key[-4:]

    def public_snapshot(self) -> dict:
        return {
            "agent": self.name,
            "base_url": self.base_url,
            "model": self.model,
            "api_key": self.masked_key(),
            "temperature": self.temperature,
            "max_steps": self.max_steps,
            "max_tokens": self.max_tokens,
            "context_budget": self.context_budget,
            "enable_thinking": self.enable_thinking,
            "search_backend": self.search_backend,
            "online": self.online,
        }

    def describe(self) -> str:
        thinking = "未指定" if self.enable_thinking is None else (
            "开启" if self.enable_thinking else "关闭")
        return "\n".join([
            "Agent    : {0}".format(self.name),
            "接口地址 : {0}".format(self.base_url),
            "模型名称 : {0}".format(self.model),
            "API 密钥 : {0}".format(self.masked_key()),
            "运行模式 : {0}".format("真实模型" if self.online else "试用模式（离线假模型）"),
            "策略参数 : 最多 {0} 步 / 温度 {1} / 单次上限 {2} token / 超时 {3} 秒".format(
                self.max_steps, self.temperature, self.max_tokens, self.timeout),
            "搜索后端 : {0}".format(self.search_backend),
            "深度思考 : {0}".format(thinking),
            "工作目录 : {0}".format(self.workspace),
            "轨迹目录 : {0}".format(self.trace_dir),
        ])