# 待确认事项

> 由主会话在运行过程中写入，等待用户拍板。

## 配置层面（来自 config/project.json 的 TODO）

- [x] `region`：主要地区 —— 中国大陆
- [x] `cutoff_date`：资料截止日期 —— 2026-10-26
- [x] `topics.*.questions`：四个方向的具体研究问题 —— 每个方向 3 问，已填入 `config/project.json`
- [x] `limits.*`：各项运行上限的数值 —— 30 来源 / 20 搜索 / 10 抓取 / 2 补充轮 / 2 重试 / 1800 秒 / 30 步 / 200 次工具调用
- [x] `model.*`：模型提供商 / 模型名 / API Key 环境变量名 / temperature —— dashscope / qwen3.7-plus / BAILIAN_TOKEN_PLAN_API_KEY / 0.2

## 每次运行后

<!-- 主会话在 runs/<run_id>/ 跑完后，把 failed / pending / 证据不足 的条目追加到这里 -->
