# 变更声明（CHANGELOG）

> 本文件记录每一轮**实质改动**：改了什么、为什么改、怎么验证、怎么回滚。
> 详细过程与实测输出在 `docs/` 下对应文档里，这里只留索引与结论。

当前仓库版本：**v3.1-ask-report-ui**（2026-11-23）

---

## 版本总览

| 版本 | 日期 | 一句话 | 详细说明 |
|---|---|---|---|
| V1 骨架 | 2026-10 | 五阶段流程 + 目录 + 交接文件 | — |
| V2 修复版 | 2026-11-17 | 真实性修复、去重、真实采集、证据核验、知识库更新、报告生成 | `docs/v2-gap-report.md`、`docs/v1-changelog.md` |
| V3 | 2026-11-23 | 打通 PDF 入库（此前抓下来的 PDF 从未进知识库）+ 环境隔离 + 联网探针 | `docs/v3-env-and-pdf-20261123.md` |
| V3.1 | 2026-11-23 | 问一句 → 带 `[Sxxx]` 出处的答案 → 导出 PDF → 网页点按钮下载 | `docs/v3.1-ask-report-ui-20261123.md` |

---

## V3.1（2026-11-23）逐项说明

### 1. 改了什么

| 文件 | 类型 | 内容 |
|---|---|---|
| `tools/ask_report.py` | 新增 | 问题 → 拆关键词 → 本地检索 → 证据去重 → 组织答案 → `output/<时间戳>_report.md`/`.pdf` |
| `tools/report_pdf.py` | 新增 | Markdown → A4 PDF（`fpdf2` + 系统中文 TTF 自动探测，`REPORT_FONT` 可覆盖） |
| `tools/web_ui.py` | 新增 | 本地网页窗口：`GET /` 提问、`POST /ask` 出结果、`GET /download/...` 下载 |
| `requirements.txt` | 修改 | 增加 `fpdf2>=2.7` |
| `README.md` | 修改 | V3.1 横幅、工具表三行、快速演示三步 |
| `PORTABLE_SETUP.md` | 修改 | 依赖说明、中文字体、§2.5 快速演示、目录表 |
| `docs/v3.1-ask-report-ui-20261123.md` | 新增 | 需求对照、实现细节、实测输出、边界与回滚 |

### 2. 为什么改

用户对最终形态的要求是："直接问一个问题，它能回答；想要的报告是 PDF 格式；有一个窗口可以下载这份报告。"

改之前：仓库只能检索（`kb_search.py` 吐 JSON），**没有任何 PDF 写出代码**，也**没有任何界面**。改之后：这条链路可以端到端跑通，并把"证据出处"做成报告里的硬结构（每条片段带 `[S001]` 与 A/B/C 等级）。

### 3. 怎么验证

```bash
# 建库
.venv\Scripts\python.exe tools/ingest.py --run-id demo

# 命令行生成报告
.venv\Scripts\python.exe tools/ask_report.py "LANMAO 睡眠记录仪与多导睡眠监测对比" --no-llm

# 网页窗口
.venv\Scripts\python.exe tools/web_ui.py     # http://127.0.0.1:8000
```

实测（2026-11-23）：

- PDF 反向校验：`页数 2 / 字符数 3447 / 含中文结论 True / 含来源编号 True`
- 网页端点：`/health 200`、`/ 200 含表单`、`POST /ask 200 6385 字节`、`/download/<pdf> 200 且首 5 字节为 %PDF-`
- 越权拦截：`/download/evil.pdf → 404`、`/download/..%2F..%2F.env → 404`

### 4. 边界（必须知道）

这一层是**呈现层**，答案来自"本地检索 + 可选的一次模型调用"，**尚未经过五个 Agent 互检**。
接入点已预留：`ask_report.answer_question()` 内的"检索 + 组织答案"换成调 `dispatcher-agent/run_cli.py` 即可，界面与 PDF 版式不用改。

未配置 `DASHSCOPE_API_KEY` 时，答案退化为"原文片段汇总"，报告里明确写"未调用模型"，不冒充推理结论。

### 5. 怎么回滚

```bash
git revert 6673fa2      # V3.1
git revert dcafbe9      # V3
```

`output/`、`inbox/`、`knowledge_base/`、`.venv/` 均在 `.gitignore` 内，回滚不影响本地数据。

---

## V3（2026-11-23）摘要

- `tools/ingest.py` 新增 `ingest_pdfs()`：扫描 `inbox/pdfs/*.pdf` 入库。**此前 `extract_pdf_text()` 是死代码，抓下来的 PDF 从未进入知识库**。
- 扫描件识别：正文 <200 字符，或 ≥3 页且平均每页 <80 字符 → 记入 `failed`，不入库、不假装成功。
- PDF 默认证据等级 `C` 并标"待人工核定"；同行评审论文由人工升级。
- 新增 `tools/probe_search.py`：验证千问 `enable_search` 在原生/兼容协议下的真实返回结构（仅 `urllib`，无 key 不发请求）。
- 环境改为项目 `.venv`，不污染系统全局 Python。

详见 `docs/v3-env-and-pdf-20261123.md`。

---

## 提交约定

1. 每轮实质改动：`git commit` + `git push`，并在本文件登记。
2. 推送失败时如实说明"未推送 + commit 号 + 恢复网络后的一条命令"，不谎称已推送。
3. 每条改动必须能回答四件事：**改了什么、为什么、怎么验证、怎么回滚**。