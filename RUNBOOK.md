# RUNBOOK · 主会话执行手册

> 主会话总控，按阶段顺序委派 5 个子智能体。子智能体之间不互相调用，只通过 `runs/<run_id>/` 下的交接文件传递结果。

## 0. 启动前检查

1. 读 `config/project.json`，确认所有 `TODO` 已被用户填完；未填的写入 `docs/decisions.md` 并**停下等用户**。
2. 检查 `inbox/`：
   - `inbox/notes/` 有会议纪要 `.md`
   - `inbox/links.md` 存在（可为空）
3. 新建本次运行目录 `runs/<run_id>/`，`run_id` 建议格式 `YYMMDD-HHMMSS-<短标签>`。
4. 在 `runs/<run_id>/role_log.jsonl` 写入首条：`{"role":"main","phase":"start","run_id":"...","timestamp":"..."}`。

## 1. 阶段一：资料收集（source-collector）

- **输入**：`inbox/`、`config/project.json`、`knowledge_base/registry.jsonl`
- **调用**：子智能体 `source-collector`
- **输出**：
  - `runs/<run_id>/01_collection.json`
  - `knowledge_base/sources/<SID>/raw.*` 与 `extracted.md`
  - `knowledge_base/cards/<SID>.md`
  - `knowledge_base/registry.jsonl` 追加
  - `knowledge_base/pending_sources.md`（只有链接/读不到的）
- **停止条件**：
  - inbox 处理完
  - 或达到 `limits.max_sources_per_run`
  - 或达到 `limits.max_tool_calls`
- **交接与用户确认**：
  1. 主会话检查 `01_collection.json` 的 `status`
  2. **询问用户**：
     - 展示收集结果摘要（成功/失败/待处理数量）
     - 如果有 `failed/pending` 项目，询问用户是否要：
       - a) 继续进入阶段二（跳过失败项）
       - b) 暂停，用户手动处理后重新运行
       - c) 启用联网搜索补充资料（修改 `web_enabled=true`）
     - 用户确认后才能进入阶段二
  3. 把 `failed/pending` 写入 `docs/decisions.md` 的"待用户处理"区

## 2. 阶段二：主题研究（topic-researcher）

- **输入**：`01_collection.json`、知识库、`config/project.json` 的 `topics`
- **调用**：对每个方向（RD/CL/AD/PC）分别调用一次 `topic-researcher`
- **输出**：`runs/<run_id>/02_research/<direction>.json`
  - 每条发现含：`question`、`finding`、`source_ids`、`locations`、`excerpts`、`gaps`
- **停止条件**：4 个方向各一份；或达到 `limits.max_steps_per_agent`
- **覆盖度汇总**：写 `runs/<run_id>/00_coverage.json`，标每个问题有多少条来源支持、多少条缺口。
- **交接与用户确认**：
  1. 主会话展示覆盖度汇总（每个方向的问题覆盖情况）
  2. **询问用户**：
     - 展示缺口列表
     - 询问用户是否要：
       - a) 补充资料（回到阶段一，计入 `limits.supplement_rounds`）
       - b) 接受当前覆盖度，进入阶段三
     - 用户确认后才能决定是否补充资料

## 3. 阶段三：证据核验（evidence-verifier）

- **输入**：`02_research/*.json`、对应原件
- **调用**：`evidence-verifier`
- **输出**：`runs/<run_id>/03_verification.json`
  - 每条关键判断：`verdict` ∈ {`supported`/`partially_supported`/`not_supported`/`unverifiable`}
  - 会议纪要中的企业自述单独标 `flag: "meeting_note_self_claim"`
- **停止条件**：所有方向的关键判断都已核验；或达到上限
- **交接与用户确认**：
  1. 主会话展示核验结果摘要（supported/partially_supported/not_supported/unverifiable 数量）
  2. **询问用户**：
     - 展示 `not_supported` / `unverifiable` 的条目列表
     - 询问用户是否要：
       - a) 保留为"证据不足"，在报告中标注
       - b) 从报告中移除这些条目
       - c) 补充资料后重新核验（回到阶段一）
     - 用户确认后才能进入阶段四
  3. 把用户决定写入 `docs/decisions.md`

## 4. 阶段四：知识库更新（knowledge-curator）

- **输入**：`03_verification.json`、现有 `knowledge_base/topics/`
- **调用**：`knowledge-curator`
- **输出**：
  - `runs/<run_id>/05_kb_update.md`（更新了什么、旧版本归档位置）
  - `knowledge_base/topics/*.md`（只更新已核验内容）
  - 旧版本归档到 `knowledge_base/topics/archive/<topic>_<timestamp>.md`
- **约束**：不新增研究结论；只把已核验发现写入主题页。
- **交接与用户确认**：
  1. 主会话展示 `05_kb_update.md`（更新了什么、旧版本归档位置）
  2. **询问用户**：
     - 展示更新内容摘要
     - 询问用户是否要：
       - a) 确认更新，进入阶段五
       - b) 撤销某些更新
       - c) 修改后重新更新
     - 用户确认后才能进入阶段五
  3. 用户确认后，正式更新 `knowledge_base/topics/*.md`

## 5. 阶段五：报告撰写（report-writer）

- **输入**：`03_verification.json`、`knowledge_base/topics/`、`00_coverage.json`
- **调用**：`report-writer`
- **输出**：
  - `runs/<run_id>/04_report.md`（草稿）
  - 用户确认后复制到 `output/<run_id>_report.md`（正式报告）
- **约束**：只用已核验发现；不引入新事实；缺口明确标出。
- **交接与用户确认**：
  1. 主会话把草稿路径 `runs/<run_id>/04_report.md` 告诉用户
  2. **询问用户**：
     - 展示报告摘要（字数、覆盖方向、缺口数量）
     - 询问用户是否要：
       - a) 确认报告，复制到 `output/<run_id>_report.md`
       - b) 修改某些部分（说明具体修改意见）
       - c) 重新生成报告
     - 用户确认后才能正式保存报告
  3. 用户确认后，复制到 `output/<run_id>_report.md`

## 6. 收尾

- 写 `runs/<run_id>/status.json`：`{status, reason, budget_used, completed_phases, failed_phases}`
- 写 `runs/<run_id>/role_log.jsonl` 末条：`{"role":"main","phase":"end",...}`
- 更新 `docs/v1-changelog.md`

## 失败与预算

- 任何阶段达到 `limits.*` 上限 → 保存已有结果，标 `status: partial`，进入收尾
- 工具不可用 → 记入 `status.json` 的 `reason`，不无限重试
- 重试计入调用次数，最多 `limits.max_retries` 次，超时 `limits.timeout_seconds`

## V2 工具说明

| 工具 | 用法 | 说明 |
|------|------|------|
| `tools/fetch_sources.py` | `--dry-run` / `--fetch --run-id ID` | 从 registry 读 pending 来源并抓取 |
| `tools/self_check.py` | `[--run-id ID]` | 自检：来源数/方向数/TODO/运行产物 |
| `tools/supplement_collector.py` | `--run-id ID [--fetch]` | 分析缺口 + 可选抓取 |
| `tools/evidence_verifier_v2.py` | `--run-id ID` | 从主题页提取 claims 并核验 |
| `tools/kb_updater.py` | `--run-id ID` | 幂等更新主题页核验状态 |
| `tools/update_cards.py` | 无参数 | 批量更新整理卡，消除 TODO |
| `tools/batch_ingest.py` | `--run-id ID` | 批量处理 inbox 下 HTML 入库 |

## 角色日志格式

`role_log.jsonl` 每行一条：

```json
{
  "role": "source-collector",
  "phase": "collect",
  "run_id": "...",
  "input_files": ["inbox/notes/..."],
  "output_files": ["runs/.../01_collection.json"],
  "tool_calls": [{"tool": "read_file", "target": "..."}],
  "status": "ok",
  "timestamp": "..."
}
```
