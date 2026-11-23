# general-domain-research-multi-agent-tool（睡眠健康 · 睡眠监测）

> **V4（2026-11-23）**：多 Agent 运行时起步 —— `shared-core/` 公共内核 + `tools/sync_core.py` 同步机制 + `research-collector-agent/`（采集，5 工具，free/qwen 双后端）+ `verify-agent/`（校验，4 工具 + 规则预检 + 红队四例）。两者自检与测试均离线通过；`qwen` 后端与模型判定因无密钥**未实测**。详见 `docs/v4-agents-collector-verify-20261123.md`。
>
> **V2 修复版（2026-11-17）**：完成资料真实性修复、去重、真实采集工具、证据核验、知识库更新和报告生成。self_check.py 全 PASS。详见 `docs/v2-gap-report.md` 和 `docs/v1-changelog.md`。
>
> **V3.1（2026-11-23）**：补上"最后一公里" —— 问一句 → 本地检索出带 `[Sxxx]` 引用的答案 → 导出 PDF → 网页里点按钮下载。新增 `tools/ask_report.py`（问答+报告）、`tools/report_pdf.py`（Markdown→PDF，中文字体）、`tools/web_ui.py`（本地网页窗口，仅监听 127.0.0.1）。详见 `docs/v3.1-ask-report-ui-20261123.md`。
>
> **V3（2026-11-23）**：打通 PDF 入库 —— `tools/ingest.py` 新增 `ingest_pdfs()`，`inbox/pdfs/` 下的论文/手册现在会真正进入知识库（此前只定义、从未调用）；扫描件自动拒收并记入 `failed`。另加 `tools/probe_search.py` 验证千问联网返回结构，并改用 `.venv` 隔离环境。详见 `docs/v3-env-and-pdf-20261123.md`。
>
> **V1 骨架**：搭好流程与目录，支持本地材料 + 联网调研。可通过 `config/project.json` 的 `web_enabled` 控制是否联网。

## 用途

让一组按角色分工的子智能体，在**主会话总控**下，按 `RUNBOOK.md` 的顺序完成：

1. 资料收集与入库（`source-collector`）
2. 分方向主题研究（`topic-researcher`）
3. 证据核验（`evidence-verifier`）
4. 知识库主题页更新（`knowledge-curator`）
5. 报告撰写（`report-writer`）

子智能体之间**不互相调用**，全部通过 `runs/<run_id>/` 下的交接文件传递结果。

## 启动方式

1. 准备环境
   - Python 3.10+
   - 依赖：`pypdf`（PDF 文本提取）、标准库即可（冒烟阶段不引入向量检索）
   - 建议用虚拟环境：`python -m venv .venv`，然后 `.venv\Scripts\python.exe -m pip install -r requirements.txt`
2. 填写配置
   - 编辑 `config/project.json`，把 `TODO` 字段按你的项目决定填入（区域、截止日期、模型等）
   - 详细说明见 `config/README.md`
3. 导入资料
   - 把会议纪要放进 `inbox/notes/`，PDF 放进 `inbox/pdfs/`（`tools/ingest.py` 会自动抽文本；扫描件会被拒收并记入 `failed`）
   - 在 `inbox/links.md` 里登记 URL
   - 联网开关：`config/project.json` 的 `web_enabled`（默认 `false`，设为 `true` 后 source-collector 可联网抓取）
4. 启动任务
   - 在主会话中告诉 Qwen Code：“按 RUNBOOK.md 跑一次 run”
   - 主会话会：建 `runs/<run_id>/` → 依次委派 5 个子智能体 → 在人工确认点停下
5. 查看结果
   - 报告：`output/`（终稿）与 `runs/<run_id>/04_report.md`（草稿）
   - 知识库：`knowledge_base/`
   - 运行记录：`runs/<run_id>/status.json`、`role_log.jsonl`

## 流程与交接

详见 `RUNBOOK.md`。每个阶段的输入/输出文件：

| 阶段 | 输入 | 输出 |
| --- | --- | --- |
| 收集 | `inbox/`、`config/project.json` | `runs/<id>/01_collection.json`、`knowledge_base/sources/*`、`cards/*`、`registry.jsonl` |
| 研究 | 上一步 + 知识库 | `runs/<id>/02_research/<direction>.json` |
| 核验 | 上一步 + 原件 | `runs/<id>/03_verification.json` |
| 知识库更新 | 上一步 | `runs/<id>/05_kb_update.md`、`knowledge_base/topics/*` |
| 报告 | 上一步 | `runs/<id>/04_report.md`、`output/*` |

## 人工参与点

每个阶段交接时都会暂停并询问用户决定：

- **启动前**：确认 `config/project.json` 中的 `TODO` 字段已填完
- **阶段一后**：确认收集结果，决定是否启用联网搜索补充资料
- **阶段二后**：查看覆盖度汇总，决定是否补充资料或进入下一阶段
- **阶段三后**：查看核验结果，决定如何处理证据不足的条目
- **阶段四后**：确认知识库更新内容
- **阶段五后**：审阅报告草稿，决定是否确认或修改

用户也可以随时在 `docs/decisions.md` 记录决策。

## 结果位置

- 正式报告：`output/<run_id>_report.md`
- 知识库主题页：`knowledge_base/topics/`
- 来源登记：`knowledge_base/registry.jsonl`
- 每次运行记录：`runs/<run_id>/`

## 多 Agent 运行时（V4，进行中）

| Agent | 目录 | 工具数 | 状态 |
|---|---|---|---|
| 采集 | `research-collector-agent/` | 5 | 离线自检通过；`free` 后端已真实命中 PubMed |
| 校验 | `verify-agent/` | 4 | 离线自检通过；规则预检 + 红队四例 4/4 |
| 知识库 / 生成 / 调度 | — | — | 未开工 |

公共内核在 `shared-core/`，改完执行 `python tools/sync_core.py`；`--check` 能发现副本被手改漂移。

```bash
cd research-collector-agent && python run_cli.py --check
cd verify-agent && python run_cli.py --check && python run_cli.py --precheck
```

每个 Agent 目录都是自包含的（有自己的 `agent/`、`.env.example`、`requirements.txt`、`run_cli.py`），可以单独拷走运行。

## 已知限制（V1）

- 联网默认关闭（`web_enabled: false`），需手动打开
- 图片附件只登记不解析（不做 OCR）
- 会议纪要标 `evidence_level: C`、`notes: 会议纪要，未独立核实`，只能当企业自述/线索
- 不写自动验收脚本，由用户人工检查

## V2 修复版新增

### 新工具
| 工具 | 功能 |
|------|------|
| `tools/fetch_sources.py` | 资料采集：读 registry 中 pending 来源，用 urllib 抓取，支持 Wikipedia REST API |
| `tools/self_check.py` | 自检：检查唯一真实来源数、每方向数、类型数、整理卡 TODO、运行产物等 |
| `tools/evidence_verifier_v2.py` | 真核验：从主题页提取 claims，用关键词+SequenceMatcher 对照原件核验 |
| `tools/kb_updater.py` | 幂等更新：归档旧版→删旧核验段→写新核验状态表格 |
| `tools/update_cards.py` | 批量更新整理卡，消除 TODO，填入摘要/关键观点/支持片段/核验状态 |
| `tools/supplement_collector.py` | 补充收集：分析缺口 + `--fetch` 调用 fetch_sources |
| `tools/ingest.py` | 入库：`inbox/notes/*.md` + **`inbox/pdfs/*.pdf`**（V3 起，pypdf 抽文本、扫描件拒收） |
| `tools/probe_search.py` | 探针：验证千问 `enable_search` 在两条协议下的真实返回结构（需 `DASHSCOPE_API_KEY`） |
| `tools/ask_report.py` | 问答：问题 → 本地检索证据 → 答案 → `output/<时间戳>_report.md/.pdf` |
| `tools/report_pdf.py` | 排版：Markdown 报告转 PDF（自动找中文字体，可用 `REPORT_FONT` 指定） |
| `tools/web_ui.py` | 网页窗口：提问、看答案与证据表、点按钮下载 PDF（标准库，只监听本机） |

## 快速演示：问一句，下载 PDF

```bash
# 1) 建库（把真实 PDF 放进 inbox/pdfs/ 后）
.venv\Scripts\python.exe tools/ingest.py --run-id demo

# 2) 命令行版
.venv\Scripts\python.exe tools/ask_report.py "LANMAO 睡眠记录仪与多导睡眠监测对比"

# 3) 网页窗口版（浏览器打开 http://127.0.0.1:8000）
.venv\Scripts\python.exe tools/web_ui.py
```

- 未配置 `DASHSCOPE_API_KEY` 时，答案退化为"原文片段汇总"，报告里会明确写"未调用模型"，不会假装是推理结论。
- PDF 页眉固定为项目名，正文含结论、证据清单表、逐条溯源与方法限制四节。

### 搜索替代方案
1. 首选：固定 URL 清单 + `fetch_sources.py` 直链抓取
2. 次选：Wikipedia REST API、PubMed E-utilities、Crossref/OpenAlex
3. 兜底：人工用浏览器保存 HTML/PDF 到 `inbox/`，再由 `batch_ingest.py` 入库
4. 通用搜索只用于发现候选 URL；任何来源必须实际抓取才能计数

### 模拟材料处理
- S027–S032 原文末尾标注「此为模拟...」，已移至 `knowledge_base/simulated_sources/`
- 在 registry 中标记 `excluded: true, type: simulated_material`
- 不计入统计，不再当真实来源引用
- 报告和主题页中不包含模拟材料内容

### 停止条件
- 抓取失败写入 `pending_sources.md`，不无限重试（最多 2 次重试，30s 超时）
- 达到 `limits.*` 上限 → 保存已有结果，标 `status: partial`
- 工具不可用 → 记入 `status.json` 的 `reason`
- `self_check.py` FAIL → 停下说明，不带病继续
