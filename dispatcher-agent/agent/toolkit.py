# -*- coding: utf-8 -*-
# AUTO-GENERATED from shared-core/toolkit.py by tools/sync_core.py — DO NOT EDIT
# CORE_VERSION: 20261123.5
"""
toolkit.py · 工具基础设施（由 shared-core 同步生成，请勿手改）

提供三样东西：沙箱、工具注册表、JSON Schema 自动生成。
各 Agent 的 tools.py 只写"本 Agent 有哪些工具"，基础设施一律走这里。
"""

from __future__ import annotations

import inspect
import json
import os
import re
import typing

_TYPE_MAP = {str: "string", int: "integer", float: "number", bool: "boolean",
             list: "array", dict: "object"}


def parse_docstring(doc):
    """从 docstring 里取「一句话说明」和 Args 段落的参数说明。"""
    if not doc:
        return "", {}
    summary_lines, arguments, section, last = [], {}, None, None
    for raw in doc.strip().splitlines():
        line = raw.strip()
        lowered = line.lower()
        if lowered.startswith(("args:", "arguments:", "parameters:", "参数:")):
            section, last = "args", None
            continue
        if lowered.startswith(("returns:", "return:", "raises:", "example:", "返回:", "示例:")):
            section, last = None, None
            continue
        if section == "args":
            match = re.match(r"^(\w+)\s*(?:\([^)]*\))?\s*[:：]\s*(.*)$", line)
            if match:
                last = match.group(1)
                arguments[last] = match.group(2).strip()
            elif last and line:
                arguments[last] += " " + line
            continue
        if line:
            summary_lines.append(line)
    return " ".join(summary_lines).strip(), arguments


def build_schema(func, name=None, description=None):
    """从函数签名 + docstring 生成给模型看的工具说明书。"""
    summary, argument_docs = parse_docstring(func.__doc__)
    try:
        hints = typing.get_type_hints(func)
    except Exception:                                          # noqa: BLE001
        hints = {}

    properties, required = {}, []
    for parameter_name, parameter in inspect.signature(func).parameters.items():
        if parameter_name in ("self", "cls"):
            continue
        python_type = hints.get(parameter_name, str)
        origin = getattr(python_type, "__origin__", None)
        json_type = ({list: "array", dict: "object"}.get(origin, "string")
                     if origin is not None else _TYPE_MAP.get(python_type, "string"))
        info = {"type": json_type}
        if parameter_name in argument_docs:
            info["description"] = argument_docs[parameter_name]
        if parameter.default is inspect.Parameter.empty:
            required.append(parameter_name)
        else:
            info["default"] = parameter.default
        properties[parameter_name] = info

    return {"type": "function", "function": {
        "name": name or func.__name__,
        "description": description or summary or func.__name__,
        "parameters": {"type": "object", "properties": properties, "required": required},
    }}


class Sandbox(object):
    """把文件操作关进一个目录。模型给的路径属于不可信输入。"""

    def __init__(self, root):
        self.root = os.path.realpath(str(root))
        os.makedirs(self.root, exist_ok=True)

    def resolve(self, relative_path):
        if not isinstance(relative_path, str) or not relative_path.strip():
            raise ValueError("路径不能为空")
        if os.path.isabs(relative_path):
            target = os.path.realpath(relative_path)
        else:
            target = os.path.realpath(os.path.join(self.root, relative_path.strip()))
        if target != self.root and not target.startswith(self.root + os.sep):
            raise PermissionError("拒绝访问：{0} 超出沙箱 {1}".format(relative_path, self.root))
        return target

    def display(self, absolute_path):
        return os.path.relpath(absolute_path, self.root).replace(os.sep, "/")


class ToolRegistry(object):
    def __init__(self):
        self._tools = {}
        self._order = []

    def register(self, func=None, name=None, description=None):
        def decorator(function):
            tool_name = name or function.__name__
            self._tools[tool_name] = {"func": function,
                                      "schema": build_schema(function, tool_name, description)}
            if tool_name not in self._order:
                self._order.append(tool_name)
            return function
        return decorator(func) if func is not None else decorator

    def register_external(self, func, name, description, parameters):
        """注册自带 JSON Schema 的外部工具（例如开源项目的解析器）。"""
        self._tools[name] = {"func": func, "schema": {"type": "function", "function": {
            "name": name, "description": description, "parameters": parameters}}}
        if name not in self._order:
            self._order.append(name)
        return func

    def names(self):
        return list(self._order)

    def schemas(self):
        return [self._tools[name]["schema"] for name in self._order]

    def describe(self):
        rows = []
        for name in self._order:
            fn = self._tools[name]["schema"]["function"]
            rows.append({"name": name, "description": fn["description"],
                         "parameters": ", ".join(fn["parameters"]["properties"]) or "无参数"})
        return rows

    def call(self, name, arguments_json, max_result_chars=6000):
        """执行工具。永远返回字符串，永远不抛异常。"""
        entry = self._tools.get(name)
        if entry is None:
            return "错误：不存在工具 {0}。可用：{1}".format(name, ", ".join(self._order))
        try:
            arguments = json.loads(arguments_json) if arguments_json else {}
            if not isinstance(arguments, dict):
                raise ValueError("参数必须是 JSON 对象")
        except (ValueError, TypeError) as exc:
            return "错误：参数不是合法 JSON（{0}）：{1}".format(exc, arguments_json)

        try:
            result = entry["func"](**arguments)
        except TypeError as exc:
            return "错误：参数不匹配（{0}）：{1}".format(exc, arguments)
        except PermissionError as exc:
            return "权限拒绝：{0}".format(exc)
        except Exception as exc:                               # noqa: BLE001
            return "错误：{0}: {1}".format(type(exc).__name__, exc)

        if not isinstance(result, str):
            result = json.dumps(result, ensure_ascii=False, default=str)
        if len(result) > max_result_chars:
            result = result[:max_result_chars] + "\n...(结果过长已截断，原文共 {0} 字符)".format(
                len(result))
        return result