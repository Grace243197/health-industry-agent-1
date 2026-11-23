# V4 变更说明：多 Agent 运行时（P1 = 采集 + 校验）

- 日期：2026-11-23
- 版本：`v4-agents-collector-verify`
- 前置：V3.1（`v3.1-ask-report-ui`）
- 范围：**只做两个 Agent**（采集、校验）+ 公共内核 + 同步机制。知识库/生成/调度尚未开工。

---

## 1. 为什么先做这两个

老师的硬性要求是「至少 2 个 Agent 互相检查」，其中"生成 + 评判"是核心。
采集和校验正好构成最小可验证的一对：

```
采集：把"外部世界"变成"带出处的来源卡"
校验：把"结论"拿回来源卡里逐字比对，判它到底有没有依据
```

这一对跑通，"双 Agent 互检"就从口号变成了可演示的东西；调度和生成可以后接，不影响这一对的独立性。

---

## 2. 架构：一个内核 + 五份配置

```
shared-core/                 ← 唯一真源（不参与运行）
  config.py   配置解析（环境变量 > .env > agentrc.DEFAULTS）
  model.py    模型客户端 + 指数退避 + 离线假模型
  core.py     ReAct 循环（步数上限/重复调用拦截/工具异常回灌/轨迹）
  memory.py   会话内记忆（裁剪 + 孤儿消息修复）
  toolkit.py  沙箱 / 工具注册表 / JSON Schema 自动生成
  prompts_base.py  三条幻觉红线 + 证据纪律 + 安全红线
tools/sync_core.py           ← 生成 + 指纹校验（CORE_VERSION = 20261123.1）
research-collector-agent/    ← 自包含，可单独拷走运行
verify-agent/                ← 同上
```

每个 Agent 目录里：

```
agent/agentrc.py    身份、默认模型、目录、离线规则     ← 手写
agent/tools.py      本 Agent 的工具                     ← 手写
agent/prompts.py    本 Agent 的岗位说明书               ← 手写
agent/{config,model,core,memory,toolkit,prompts_base}.py ← 生成，勿手改
run_cli.py  .env.example  requirements.txt  selftest.py  tests/
```

改内核只改 `shared-core/`，然后 `python tools/sync_core.py`；
`python tools/sync_core.py --check` 能发现谁被手改漂移了。

---

## 3. 两个 Agent 各做了什么

### 3.1 采集 Agent（`research-collector-agent/`）

**五个工具**（与任务书 01 一致）：`web_search` / `web_fetch` / `save_file` / `read_file` / `list_dir`。

**两个检索后端 + 合并模式**（同一 Agent，配置切换）：

| 后端 | 实现 | 状态 |
|---|---|---|
| `free` | PubMed E-utilities、Europe PMC、OpenAlex、Wikipedia REST | ✅ 已实测（见下） |
| `qwen` | DashScope 原生协议 `enable_search` + `search_options.enable_source` | ⚠️ 代码就绪，**未实测**（无密钥） |
| `both` | 两路合并，按 URL 去重，保留 `discovered_by` | 待有 key 后 A/B |

**纪律**（写进工具说明与提示词）：
- 搜索只给"候选线索"，数字/摘要不得直接写进来源卡；
- 正文必须 `web_fetch` 抓取，并记录**最终 URL**与抓取时间；
- 抓不到就写"抓取失败"，不用摘要补位；
- PDF 抽不出文字就明说需要 OCR。

### 3.2 校验 Agent（`verify-agent/`）

**四个工具**：`grep_source` / `read_file` / `list_dir` / `save_file`。

- `grep_source` 是"逐字比对"的物理基础：在 `sources/` 里正则检索，返回文件名 + 行号 + 原文行。**找不到就是找不到**，不靠模型记忆。
- 读写权限分离：可读 `sources/`、`claims/`，**只能写 `verifications/`**。
- 四值判定：`verified` / `partially_supported` / `contradicted` / `insufficient`。
- 三条红线（常识冒充原文、个案推通则、来源张冠李戴）写进提示词与判定口径。

**另外加了一个不调模型的"规则预检"**（`python run_cli.py --precheck`）：
先按"数字是否出现 + 措辞重合度"打一个确定性初判，给模型和人工排序用。
报告里明确标注"规则预检，非模型判定"，不冒充 verdict。

---

## 4. 实测结果

### 4.1 自检（不联网、不花钱）

```bash
python tools/sync_core.py --check
# [OK] research-collector-agent 内核版本 20261123.1
# [OK] verify-agent 内核版本 20261123.1

cd research-collector-agent && python run_cli.py --check
# 工具数量 : 5
# 工具清单 : web_search, web_fetch, save_file, read_file, list_dir
# [OK] 自检通过（未联网、未消耗额度）

cd verify-agent && python run_cli.py --check
# 工具数量 : 4
# [OK] 自检通过
```

自检里有一条硬约束：**提示词提到的工具名必须与真实注册的工具集完全一致**。
第一次跑就抓到了真问题——`prompts.py` 只写了 `web_search`/`web_fetch`，没提 `save_file`/`read_file`/`list_dir`，模型会不知道有这些工具。已修。

### 4.2 免费检索真跑（真实网络）

```bash
python run_cli.py --task "搜索 CPAP adherence cardiovascular outcomes" --offline
```

```
工具序列: web_search
耗时: 4.92 秒
[1] Mandibular advancement device vs continuous positive airway pressure ...
    URL: https://pubmed.ncbi.nlm.nih.gov/43067176/
```

PubMed 真实返回，说明 `free` 后端可用；`--offline` 只作用于模型（用假模型），工具照常联网。

### 4.3 规则预检跑 W2 真实数据

把 `W2/knowledge/source_cards/*.md`（8 份）与 `claims_rd.json`、`claims_clinics.json`（16 条断言）拷进 `sources/`、`claims/`：

```bash
python run_cli.py --precheck
```

16 条全部出结论，分布：`verified` 4 条、`partially_supported` 9 条、`insufficient` 3 条、`contradicted` 0 条。

**必须说明的偏差**：W2 的来源卡本身就是同一套流程写的，措辞与 claim 高度重合，
所以规则预检在这批数据上会**偏宽松**（verified 偏多）。它只能当排序信号，不能当最终判定。
真正可信的验证是下面这组可判定的红队用例。

### 4.4 红队四例（可判定）

`verify-agent/tests/test_precheck.py`，固定语料 `SRC007`：

| 用例 | 构造 | 期望 | 实测 |
|---|---|---|---|
| 逐字一致 | 与原文完全相同 | verified | ✅ |
| 篡改数字 | 7 名受试者 → 700 名 | contradicted | ✅ |
| 无关内容 | 价格/CE 认证（原文没提） | insufficient | ✅ |
| 过度概括 | 「居家单通道 EEG」→「取代 PSG 做临床诊断」 | partially/insufficient | ✅ |

```bash
cd verify-agent && python -m unittest discover -s tests
# Ran 8 tests — OK
cd research-collector-agent && python -m unittest discover -s tests
# Ran 5 tests — OK
```

---

## 5. 借鉴了哪些开源项目（以及还没借鉴的）

| 已落地 | 来源 | 具体借了什么 |
|---|---|---|
| ReAct 循环 + 步数预算 + 重复调用拦截 | Tongyi DeepResearch（20.2k, Apache-2.0） | "思考→行动→观察"的循环骨架与终止条件 |
| 搜索只给线索、正文必须抓 | GPT Researcher（30.8k, Apache-2.0） | source-tracking 纪律：引用必须指向实际抓到的原文 |
| claim 级逐条核对 | FactScore 的方法论 | 把结论拆成原子断言，逐条找支持片段 |
| 先批判再判定 | open_deep_research（12.7k, MIT，已归档） | reflection 顺序：先找反证，再给结论 |

**尚未落地（下一轮）**：
- GPT Researcher 的 planner 拆子问题 + 并发执行 + 上下文压缩（当前是模型自主决定检索轮次，提示词限制最多 3 轮）；
- Khoj 的 BM25 + 精排两阶段检索（知识库 Agent 才需要）；
- 调度 Agent 的 supervisor 路由与回退。

这些没做，是因为它们分别属于知识库/调度环节，不在本轮范围。**不把"计划借鉴"写成"已经借鉴"。**

---

## 6. 还没做的（诚实清单）

| 缺口 | 影响 |
|---|---|
| `qwen` 检索后端未实测 | 无密钥；`search_info` 的真实层级仍未确认，代码按"找不到就返回空 + 原因"写 |
| 采集不会自动拆子问题 | 一次任务靠模型自己换关键词，最多 3 轮 |
| 校验的最终 verdict 未跑过真实模型 | 只有规则预检 + 红队；模型判定要等 key |
| 知识库/生成/调度三个 Agent | 未开工 |
| 未接入 `ask_report` / 网页 | 目前两条线独立；接入点在 `answer_question()` |

---

## 7. 怎么用

```bash
# 0) 环境（已有可跳过）
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt

# 1) 改完内核后同步
.venv\Scripts\python.exe tools/sync_core.py

# 2) 采集：自检 / 跑任务
cd research-collector-agent
..\..\.venv\Scripts\python.exe run_cli.py --check
..\..\.venv\Scripts\python.exe run_cli.py --task "搜索 CPAP 依从性研究"

# 3) 校验：自检 / 规则预检 / 测试
cd ..\verify-agent
..\..\.venv\Scripts\python.exe run_cli.py --check
..\..\.venv\Scripts\python.exe run_cli.py --precheck
..\..\.venv\Scripts\python.exe -m unittest discover -s tests
```

---

## 8. 回滚

```bash
git revert <本次提交哈希>
```

新增的 `shared-core/`、两个 Agent 目录、`tools/sync_core.py` 全部独立，不影响 V3/V3.1 的问答与 PDF 链路。
`*/sources/`、`*/traces/`、`verify-agent/claims|verifications/` 已在 `.gitignore` 内。