# 变更声明（CHANGELOG）

> 本文件记录每一轮**实质改动**：改了什么、为什么改、怎么验证、怎么回滚。
> 详细过程与实测输出在 `docs/` 下对应文档里，这里只留索引与结论。

当前仓库版本：**v5-generator-dispatcher**（2026-11-23）

---

## 版本总览

| 版本 | 日期 | 一句话 | 详细说明 |
|---|---|---|---|
| V1 骨架 | 2026-10 | 五阶段流程 + 目录 + 交接文件 | — |
| V2 修复版 | 2026-11-17 | 真实性修复、去重、真实采集、证据核验、知识库更新、报告生成 | `docs/v2-gap-report.md`、`docs/v1-changelog.md` |
| V3 | 2026-11-23 | 打通 PDF 入库（此前抓下来的 PDF 从未进知识库）+ 环境隔离 + 联网探针 | `docs/v3-env-and-pdf-20261123.md` |
| V3.1 | 2026-11-23 | 问一句 → 带 `[Sxxx]` 出处的答案 → 导出 PDF → 网页点按钮下载 | `docs/v3.1-ask-report-ui-20261123.md` |
| V4 | 2026-11-23 | 多 Agent 运行时起步：公共内核 + 同步机制 + 采集 Agent + 校验 Agent | `docs/v4-agents-collector-verify-20261123.md` |
| V5 | 2026-11-23 | 生成 Agent（双源强制 + 证据索引）+ 调度 Agent（subprocess 隔离 + 审计 + 回退一次） | `docs/v5-generator-dispatcher-20261123.md` |

---

## V5（2026-11-23）逐项说明

### 1. 改了什么

| 路径 | 类型 | 内容 |
|---|---|---|
| `generator-agent/` | 新增 | 5 工具；`preflight()` 双源强制；证据索引带 A/B/C |
| `dispatcher-agent/` | 新增 | 7 工具；subprocess 调下游 + 超时/失败如实回报 + `audit/audit_log.jsonl` |
| `shared-core/core.py` | 修改 | 新增 `after_tools` 扩展点，供调度实现"驳回回退一次" |
| `shared-core/model.py` | 修改 | `$q` 清洗任务动词；新增 `$task` 透传原句 |
| `shared-core/config.py` | 修改 | 增加 `settings` / `project_root` / `project_path` |
| `tools/sync_core.py` | 修改 | 内核版本 `20261123.5`；修复被 PowerShell 改坏的文件 |
| `docs/v5-...md`、`README.md`、`.gitignore` | 新增/修改 | 文档与运行产物忽略 |

### 2. 为什么

老师要求"生成 + 评判互相检查"。生成 Agent 与校验 Agent 配对后，才能构成真正的互检闭环；
调度 Agent 是"用户只和一个入口对话"的落点，也是"部署隔离"的证明。

### 3. 怎么验证

```bash
python tools/sync_core.py --check                         # 4 个 Agent 指纹一致 20261123.5
cd generator-agent && python run_cli.py --check           # 5 工具；双源缺失时拒绝生成
cd dispatcher-agent && python run_cli.py --check          # 7 工具；3 个下游存在，知识库缺失 WARN
```

实测：四个 Agent 单元测试 5+8+9+10=32 全过；调度真实调用采集成功（27.9 秒），
审计落 1 行，下游返回 European PMC 的 OSAHS 监测文献。

### 4. 本轮修掉的三个真 bug

1. 生成 Agent 中文检索把整句当一个 token → 改为二元组切分，整句也能命中。
2. 调度子进程 UTF-8/GBK 编码不一致 → "驳回"识别失败；改为注入 `PYTHONIOENCODING=utf-8`。
3. `$q`（检索词）与 `$task`（原句）混用 → 下游拿不到动词不干活；拆成两个占位符。

另有一次自伤事故：用 PowerShell `Set-Content` 改含中文的 `sync_core.py`，导致 UTF-8 被读成 ANSI、
注释与代码粘连报 `IndentationError`；已整份重写，并记录"此机器不要用 PowerShell 改中文源文件"。

### 5. 边界

- **知识库 Agent 仍未实现**，`run_knowledge` 会如实返回"入口不存在"；
- 全部只跑过离线假模型，真实生成质量与 verdict 未验证；
- 完整四段链路（采集→知识库→生成→校验）尚未串通；
- `ask_report` / 网页仍走 V3.1 自己的链路。

详见 `docs/v5-generator-dispatcher-20261123.md`。

---

## V4（2026-11-23）逐项说明

### 1. 改了什么

| 路径 | 类型 | 内容 |
|---|---|---|
| `shared-core/` | 新增 | 唯一真源：`config / model / core / memory / toolkit / prompts_base` 六个文件 |
| `tools/sync_core.py` | 新增 | 把内核分发到各 Agent 目录，`--check` 比对指纹（CORE_VERSION `20261123.1`） |
| `research-collector-agent/` | 新增 | 采集 Agent：5 个工具，`free`/`qwen`/`both` 三个检索后端 |
| `verify-agent/` | 新增 | 校验 Agent：4 个工具 + 规则预检 + 红队四例 |
| `.gitignore` | 修改 | 忽略 `*/sources|traces|claims|verifications` 等运行产物 |
| `README.md` | 修改 | V4 横幅与多 Agent 使用说明 |

### 2. 为什么这么切

- **一个内核 + 五份配置**：五个 Agent 的差别只有"提示词、工具集、产物格式、模型与步数"，没必要写五套循环。
- **每个目录自包含**：任务书要求能进目录跑 `run_cli.py`，老师要看"部署隔离"，所以内核是生成进去的副本，靠 `sync_core.py` 防漂移。
- **先做采集 + 校验**：这是"≥2 个 Agent 互相检查"的最小可验证闭环，且不依赖知识库/调度先完工。

### 3. 怎么验证

```bash
python tools/sync_core.py --check                          # 两个 Agent 内核指纹一致
cd research-collector-agent && python run_cli.py --check   # 5 个工具，[OK]
cd verify-agent && python run_cli.py --check               # 4 个工具，[OK]
python run_cli.py --precheck                               # 16 条 W2 断言出初判
python -m unittest discover -s tests                       # 红队四例 + 内核冒烟
```

实测：采集 `free` 后端真实命中 PubMed（4.92 秒）；红队四例 4/4 符合预期；测试 5 + 8 全过。

### 4. 边界（不许含糊）

- `qwen` 检索后端**未实测**（无密钥），`search_info` 的真实层级仍未确认；
- 采集**没有**自动拆子问题（GPT Researcher 的 planner 属下一轮）；
- 校验的最终 verdict **没有**跑过真实模型，现有的是规则预检 + 红队；
- 知识库 / 生成 / 调度三个 Agent 未开工；
- 尚未接入 `ask_report`，问答页仍走 V3.1 自己那条链路。

详见 `docs/v4-agents-collector-verify-20261123.md`。

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