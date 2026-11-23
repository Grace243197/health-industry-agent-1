# -*- coding: utf-8 -*-
"""
============================================================
 千问联网能力探针  probe_search.py
============================================================

【这个脚本解决什么问题】

我们要用千问的 enable_search 做「候选 URL 发现器」，但官方文档只说了
`search_info.search_results`，没写清它在原生协议和 OpenAI 兼容模式下
到底挂在哪一层、字段叫什么。**照着文档猜着写代码，是最容易埋雷的做法。**

所以先写这个探针：只发一次请求，把真实返回结构打印出来。
拿到事实之后再写正式工具，避免"文档对、代码错"。

【两种协议的区别（本脚本会分别验证）】

  原生 protocol（dashscope.aliyuncs.com/api/v1/...）
      参数放在 parameters 里，能开 search_options.enable_source
      预期能拿到来源链接

  OpenAI 兼容 protocol（compatible-mode/v1/chat/completions）
      参数要透传，官方明确说拿不到来源 url —— 本脚本用来证实这一点

【用法】

    set DASHSCOPE_API_KEY=sk-xxxx
    python probe_search.py --query "成人睡眠呼吸监测 行业 市场规模 2025"
    python probe_search.py --mode compat --show-raw

（仓库里放在 tools/probe_search.py，本地工作区放在 scripts/，内容一致。）

没有密钥时脚本不会发请求，只打印获取方式并以退出码 2 结束。

【纪律提醒】

enable_search 返回的 content 是**模型改写过的答案**，不是网页原文。
它只能用来发现候选链接；正文必须自己抓，否则会撞「常识冒充原文」这条红线。
"""

from __future__ import annotations

import argparse
import datetime
import json
import os
import sys

NATIVE_URL = "https://dashscope.aliyuncs.com/api/v1/services/aigc/text-generation/generation"
COMPAT_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions"

# 从上到下依次找 .env：当前目录、项目根、仓库 config/、教学 demo 目录
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ENV_CANDIDATES = list(dict.fromkeys([
    os.path.join(os.getcwd(), ".env"),
    os.path.join(_ROOT, ".env"),
    os.path.join(_ROOT, "config", ".env"),
    os.path.join(_ROOT, "agent_demo_submit", "v1", "code", ".env"),
]))


def load_key():
    """按 环境变量 → .env 文件 的顺序找密钥。"""
    key = os.environ.get("DASHSCOPE_API_KEY") or os.environ.get("AGENT_API_KEY")
    if key:
        return key.strip(), "环境变量"

    for path in ENV_CANDIDATES:
        if not os.path.isfile(path):
            continue
        for raw_line in open(path, encoding="utf-8"):
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            name, _, value = line.partition("=")
            if name.strip() in ("DASHSCOPE_API_KEY", "AGENT_API_KEY"):
                value = value.strip().strip('"').strip("'")
                if value:
                    return value, path
    return "", None


def build_native_payload(model, query):
    """原生协议：搜索参数放在 parameters 里。"""
    return {
        "model": model,
        "input": {"messages": [{"role": "user", "content": query}]},
        "parameters": {
            "result_format": "message",
            "enable_search": True,
            "search_options": {
                "enable_source": True,        # 关键：要求返回 search_info
                "forced_search": True,        # 强制走搜索，别让模型凭记忆答
                "search_strategy": "turbo",   # 最便宜档，候选发现够用
            },
        },
    }


def build_compat_payload(model, query):
    """OpenAI 兼容协议：搜索参数平铺在请求体里。"""
    return {
        "model": model,
        "messages": [{"role": "user", "content": query}],
        "enable_search": True,
        "search_options": {"enable_source": True, "forced_search": True,
                           "search_strategy": "turbo"},
    }


def post(url, key, payload, timeout):
    """用标准库发请求，和仓库其它 tools 保持一致（不引入 requests）。"""
    import urllib.error
    import urllib.request

    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=data,
        method="POST",
        headers={"Authorization": "Bearer " + key, "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            status = response.status
            raw = response.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:        # 4xx/5xx 也要把响应体打出来，否则没法排查
        status = exc.code
        raw = exc.read().decode("utf-8", errors="replace")

    try:
        return status, json.loads(raw)
    except ValueError:
        return status, {"_raw_text": raw[:2000]}


def find_search_info(node, path="root"):
    """递归找出所有 search_info 节点，返回 [(路径, 节点)]。

    这里不假设文档说的层级是对的 —— 只按事实找。
    """
    found = []
    if isinstance(node, dict):
        for key, value in node.items():
            here = path + "." + key
            if key == "search_info":
                found.append((here, value))
            found.extend(find_search_info(value, here))
    elif isinstance(node, list):
        for index, value in enumerate(node):
            found.extend(find_search_info(value, "{0}[{1}]".format(path, index)))
    return found


def report(mode, status, body, show_raw):
    print("\n" + "=" * 68)
    print("模式：{0}    HTTP {1}".format(mode, status))
    print("=" * 68)

    if status != 200:
        print(json.dumps(body, ensure_ascii=False, indent=2)[:2000])
        return False

    # ---- 1. 正文长度（判断有没有真的联网）----
    content = ""
    try:
        if mode == "native":
            content = body["output"]["choices"][0]["message"]["content"]
        else:
            content = body["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError):
        content = ""
    print("正文长度：{0} 字符".format(len(content or "")))
    print("正文开头：{0}".format((content or "")[:120].replace("\n", " ")))

    # ---- 2. 找来源链接 ----
    hits = find_search_info(body)
    if not hits:
        print("search_info：未找到 —— 该协议拿不到来源链接")
    for path, info in hits:
        print("search_info 位置：{0}".format(path))
        results = (info or {}).get("search_results") if isinstance(info, dict) else None
        if not results:
            print("  但里面没有 search_results，实际字段：{0}".format(
                list(info.keys()) if isinstance(info, dict) else type(info).__name__))
            continue
        print("  共 {0} 条来源，首条字段：{1}".format(
            len(results), list(results[0].keys()) if isinstance(results[0], dict) else "?"))
        for item in results[:3]:
            if isinstance(item, dict):
                print("   - {0} | {1}".format(item.get("site_name", "?"),
                                             item.get("url", "?")))

    if show_raw:
        print("\n---- 原始响应 ----")
        print(json.dumps(body, ensure_ascii=False, indent=2)[:8000])

    return True


def main():
    parser = argparse.ArgumentParser(description="验证千问 enable_search 的真实返回结构")
    parser.add_argument("--query", default="成人睡眠呼吸监测 行业 市场规模 2025",
                        help="测试用的查询词")
    parser.add_argument("--model", default="qwen-plus", help="模型名，默认 qwen-plus")
    parser.add_argument("--mode", choices=("native", "compat", "both"), default="both",
                        help="测哪种协议，默认两种都测")
    parser.add_argument("--timeout", type=int, default=60)
    parser.add_argument("--show-raw", action="store_true", help="打印完整原始 JSON")
    parser.add_argument("--save", action="store_true", help="把原始响应存到 scripts/probe_output/")
    args = parser.parse_args()

    key, source = load_key()
    if not key:
        print("未找到 DASHSCOPE_API_KEY。")
        print("请先设置环境变量，或在下列位置新建 .env：")
        for path in ENV_CANDIDATES:
            print("  " + path)
        print("\n.env 内容示例：\n  DASHSCOPE_API_KEY=sk-xxxxxxxx")
        print("\n（也可以复用 AGENT_API_KEY 这个名字。）")
        return 2

    print("密钥来源：{0}；模型：{1}；查询：{2}".format(source, args.model, args.query))

    modes = ("native", "compat") if args.mode == "both" else (args.mode,)
    outputs = {}
    for mode in modes:
        url = NATIVE_URL if mode == "native" else COMPAT_URL
        payload = build_native_payload(args.model, args.query) if mode == "native" \
            else build_compat_payload(args.model, args.query)
        try:
            status, body = post(url, key, payload, args.timeout)
        except Exception as exc:                                  # noqa: BLE001
            print("\n[{0}] 请求失败：{1}: {2}".format(mode, type(exc).__name__, exc))
            print("如果是网络问题，先确认能访问 dashscope.aliyuncs.com。")
            continue
        outputs[mode] = {"status": status, "body": body}
        report(mode, status, body, args.show_raw)

    if args.save and outputs:
        out_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "probe_output")
        os.makedirs(out_dir, exist_ok=True)
        stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
        path = os.path.join(out_dir, "{0}-probe.json".format(stamp))
        with open(path, "w", encoding="utf-8") as file:
            json.dump({"query": args.query, "model": args.model, "results": outputs},
                      file, ensure_ascii=False, indent=2)
        print("\n已保存：{0}".format(path))
        print("注意：这份文件里是模型输出，可能含引用文本，提交前自己看一眼。")

    return 0 if any(item["status"] == 200 for item in outputs.values()) else 1


if __name__ == "__main__":
    sys.exit(main())