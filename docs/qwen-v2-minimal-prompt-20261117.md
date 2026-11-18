# 给千问 Desktop 的 V2 收口 Prompt（2026-11-17）

你是本项目的执行智能体。项目根目录：

`D:\新建文件夹\one\大三上\健康行业实践\general-domain-research-multi-agent-tool`

## 目标

只做 **V2 验收收口**，不补新内容、不换框架、不做 12 月新领域改造。

完成后应满足 `docs/v2-gap-report.md` §5 的全部验收标准：

- 唯一真实来源 ≥30，每方向 ≥6，类型 ≥4（当前已达标，不要动）
- 4 个岗位各有交代（当前已写"未找到真实招聘样本"，保留，不要编造）
- 9 个主题页齐全，无未闭合注释、无重复核验段
- 整理卡 0 TODO、有核验状态（当前已达标，不要动）
- 运行产物齐全，报告不是旧报告复制，引用可追溯
- `self_check.py --run-id 261117-v2-final` 全 PASS

**已达标、禁止改动**：registry 的 32 份真实来源、S027–S032 的排除处理、4 个岗位页的"未找到真实招聘样本"声明、32 张整理卡的主体内容。

## 先读

1. `docs/v2-gap-report.md` §5
2. `runs/261117-v2-final/` 下全部产物
3. `tools/evidence_verifier_v2.py`、`tools/kb_updater.py`、`tools/self_check.py`

## 执行顺序（不要跳步）

### 任务 0：备份

```bash
cp -r runs/261117-v2-final runs/261117-v2-final.bak-20261117
```

不删除任何旧文件。

---

### 任务 1：修岗位页 claim 提取 bug，重跑核验

**文件**：`tools/evidence_verifier_v2.py` 约第 110–111 行

当前代码：

```python
section_match = re.search(rf'##.*{section_name}.*\n(.*?)(?=\n##\s|\Z)', content, re.DOTALL)
```

`re.DOTALL` 让 `.*` 跨行吞掉整节，`group(1)` 为空，4 个岗位页提取出 0 条 claim。

改为：

```python
section_match = re.search(
    rf'^##[^\n]*{re.escape(section_name)}[^\n]*\n(.*?)(?=\n##[ \t]|\Z)',
    content, re.DOTALL | re.MULTILINE
)
```

执行：

```bash
export PYTHONIOENCODING=utf-8
python tools/evidence_verifier_v2.py --run-id 261117-v2-final
```

预期：

- `pages_covered` 从 9 变为 **13**
- `total_claims` 大于 89
- 4 个岗位页的职责类判断因无 `source_id` 被判 `unverifiable`，这是正确结果
- 不允许给岗位页编造 `source_id`，不允许把 `unverifiable` 手工改成 `supported`

更新 4 个岗位页末尾的核验状态：

- `knowledge_base/topics/job_sleep_physician.md`
- `knowledge_base/topics/job_sleep_technologist.md`
- `knowledge_base/topics/job_sleep_center_admin.md`
- `knowledge_base/topics/job_sleep_health_educator.md`

把：

```markdown
- 待核验（岗位页尚未纳入 evidence_verifier_v2 覆盖范围）
```

改为：

```markdown
- 已纳入核验；因未找到真实招聘样本，岗位职责类判断标记为 unverifiable。
```

---

### 任务 2：跑知识库更新，补出 05_kb_update.md

```bash
python tools/kb_updater.py --run-id 261117-v2-final
```

预期：

- 生成 `runs/261117-v2-final/05_kb_update.md`
- 9 个主题页各追加一个 `## 核验状态` 段
- 每个主题页只有一个 `## 核验状态`，没有重复
- 旧版本已归档到 `knowledge_base/topics/archive/`

再运行一次同样的命令，确认幂等：每个主题页仍然只有一个 `## 核验状态`，没有重复段落。第二次运行后保留最终结果即可。

---

### 任务 3：把抓取记录改成如实记录（不联网）

**问题**：`runs/261117-v2-final/01_fetch_manifest.json` 共 10 条，只有 S040、S042 有真实 URL/sha256/15:55 时间戳；S033–S039、S041 共 8 条是 `url=N/A`、`text_chars=0`、`timestamp=17:12` 的占位，却记 `success=true`。`status.json` 的 `web_fetches=10` 与事实不符。

本次采用**复用记录**方案，不重新抓取，避免改动已核验的原文：

1. 重写 `01_fetch_manifest.json`。10 条统一按以下字段填写：

   - `source_id`
   - `url`：从 `knowledge_base/registry.jsonl` 的 `url_or_path` 读取（不得为 N/A）
   - `final_url`：从 `canonical_url` 读取
   - `status`：S040、S042 保留原值 200；其余 8 条填 `null`（本次未发起 HTTP 请求）
   - `sha256`：`knowledge_base/sources/<SID>/raw.html` 的文件哈希
   - `sha256_scope`: `"raw.html"`
   - `text_chars`：`extracted.md` 的字符数（必须 > 0）
   - `elapsed`：S040、S042 保留原值；其余 8 条填 `null`
   - `success`：`true`（原件存在且可读）
   - `timestamp`：`raw.html` 的 mtime，ISO 格式
   - `timestamp_source`: `"file_mtime"`
   - `fetched_in_this_run`: `false`
   - `reused`: `true`
   - `reused_from`: S040/S042 填 `"261117-v2-fix"`；其余 8 条填 `"prior_batch_2026-11-17T15:40-15:42"`
   - `note`: `"本次运行未重新联网抓取；复用已保存原件"`

   顶层字段：

   ```json
   {
     "run_id": "261117-v2-final",
     "total": 10,
     "success": 10,
     "fetched_in_this_run": 0,
     "reused": 10
   }
   ```

2. 更新 `status.json` 的 `budget_used`：

   ```json
   "budget_used": {
     "sources_collected": 32,
     "web_fetches": 0,
     "reused_sources": 10,
     "supplement_rounds": 0
   }
   ```

   并在 `status.json` 增加：

   ```json
   "note": "本次运行未重新联网抓取；10 份来源复用自已保存原件"
   ```

3. 更新 `01_collection.json` 的 `tool_calls`，只写实际发生的事：

   ```json
   "tool_calls": [
     {"tool": "local_reuse", "action": "load S033-S042 from knowledge_base/sources", "count": 10},
     {"tool": "manual_registry_edit", "action": "标记 S027-S032 excluded、S013/S016/S018/S026 duplicate", "count": 10}
   ]
   ```

   `new_fetched` 可保留 S033–S042，但增加说明：

   ```json
   "new_fetched_note": "新入知识库 10 份；其中 2 份来自 261117-v2-fix，8 份来自 2026-11-17 15:40-15:42 批次；本次运行未重新抓取"
   ```

4. 在 `knowledge_base/pending_sources.md` 末尾增加：

   ```markdown
   ## 抓取日志缺口（建议下轮重抓）

   - S033–S039、S041：原件存在，但缺少独立抓取日志（raw.html mtime 2026-11-17 15:40–15:42）。
   - 建议下次联网时用 `fetch_sources.py --force` 重抓并生成完整 manifest。
   ```

**硬性要求**：manifest 中不允许出现 `success=true` 但 `url=N/A`、`sha256=null` 或 `text_chars=0` 的条目。

---

### 任务 4：重写 role_log.jsonl（真实时间戳、真实工具）

当前 `role_log.jsonl` 所有阶段时间戳都是 `2026-11-17T17:12:21`，且引用了不存在的 `fix_registry.py`、`generate_report`、`read_topic_pages`、`extract_findings`。

重写规则：

- 每个阶段完成后立即追加一行，用 `date -Iseconds` 取真实时间；时间必须递增，不能全部相同。
- 只记录实际存在的工具和实际发生的动作。
- 手工修改报告就写 `{"tool":"manual_edit","target":"runs/261117-v2-final/04_report.md"}`，不要写 `generate_report`。
- 不要写 `fix_registry.py`；一次性的 registry 操作写 `manual_registry_edit`。
- 每条保留 `role`、`phase`、`run_id`、`input_files`、`output_files`、`tool_calls`、`status`、`timestamp`。
- 阶段顺序：`start` → `collect` → `research` → `verify` → `curate` → `report` → `end`。

`verify` 阶段的 `tool_calls` 写：

```json
[{"tool": "evidence_verifier_v2.py", "target": "9 topic pages + 4 job pages", "claims_extracted": <重跑后的数字>}]
```

`curate` 阶段写：

```json
[{"tool": "kb_updater.py", "target": "9 topic pages"}, {"tool": "update_cards.py", "target": "32 cards"}]
```

（`update_cards.py` 只写进日志，如果本次没有重新运行，就不要写它。）

---

### 任务 5：统一报告数字，删除重复章节

先取当前数字：

```bash
python - <<'EOF'
import json
d = json.load(open('runs/261117-v2-final/03_verification.json', encoding='utf-8'))
print('total_claims =', d['total_claims'])
print('pages_covered =', d['pages_covered'])
print('verdict_summary =', d['verdict_summary'])
EOF
```

来源构成的正确数字：

- 32 份唯一真实来源
- 27 份 `popular`（均为 Wikipedia）
- 2 份 `meeting_note`
- 2 份 `guideline`：S039（NHS）、S041（WHO）
- 1 份 `institutional`：S038（ResMed）
- 证据等级：30 份 C 级，2 份 B 级（S039、S041）

修改 `runs/261117-v2-final/04_report.md`（用 grep 定位，不要只依赖行号）：

1. `共核验 89 条判断，覆盖 9 个主题页` → 改为 JSON 的 `total_claims`，并写"覆盖 13 个页面（9 个主题页 + 4 个岗位页）"。
2. `核验 86 条判断中 5 条 supported、53 条 partially_supported、28 条 not_supported` → 改为 JSON 的数字。
3. `86 条核验判断：supported=5, partially_supported=53, not_supported=28, unverifiable=0` → 改为 JSON 的数字。
4. `Wikipedia 百科（28 份）` → `Wikipedia 百科（27 份）`。
5. `指南（1 份，NHS）` → `指南（2 份：NHS、WHO）`。
6. `28 份为 Wikipedia 百科条目` → `27 份为 Wikipedia 百科条目`。
7. `1 份 NHS 指南（B 级）` → `2 份指南（NHS、WHO，B 级）`。
8. `popular（Wikipedia 28 份）` → `popular（Wikipedia 27 份）`，并在同表补上 `guideline（NHS、WHO 各 1 份）`。
9. 所有 `覆盖 9 个主题页` → `覆盖 13 个页面（9 个主题页 + 4 个岗位页）`。

同步修改 `knowledge_base/topics/cross_direction_synthesis.md` 第 10、18 行的来源构成与核验数字。

**删除重复章节**：

只处理以下 8 个重复的 `###` 标题，每个只保留一个：

- `### 2.5 分歧与限制`、`### 2.6 信息缺口`
- `### 3.5 分歧与限制`、`### 3.6 信息缺口`
- `### 4.5 分歧与限制`、`### 4.6 信息缺口`
- `### 5.5 分歧与限制`、`### 5.6 信息缺口`

做法：保留第一次出现的段落；把第二次段落中**不重复的要点**合并进去；删除第二个标题及其块。合并后同一标题只出现一次。

**不要动**以下重复项，它们是 4 个岗位页各自的子标题，属于正常结构：

- `### 2.1 临床诊疗`、`### 2.2 监测解读` 等
- `### 3.1 教育背景`、`### 3.2 专业知识`、`### 3.3 技能要求`、`### 3.4 资质认证`
- `### 4.1 数据来源说明`、`### 4.2 职业发展路径`、`### 4.3 工作场景`
- 4 个 `## 一、岗位概述`

如果合并时无法判断某段是否重复，**停下来说明**，不要直接删。

最后同步 output：

```bash
cp runs/261117-v2-final/04_report.md output/261117-v2-final_report.md
```

**禁止**改结论、增删来源、改写判断；只改数字、去重、同步。

---

### 任务 6：归档旧报告

```bash
mkdir -p output/archive
mv output/261117-v2-fix_report.md output/archive/
mv output/261117-v2-full_report.md output/archive/
mv output/v2_run1_report.md output/archive/
```

更新 `docs/v1-changelog.md` 中引用这三个文件的路径，改为 `output/archive/...`。

不删除文件。

---

## 可选加分项（非 V2 硬门槛，时间够再做）

1. **Wikipedia 搜索适配器**：新建 `tools/search_sources.py`，调用
   `https://en.wikipedia.org/w/api.php?action=query&list=search&srsearch=<query>&format=json`，
   支持 `--query`、`--limit`、`--run-id`，把候选标题/摘要/URL 写入
   `runs/<run_id>/search_results.json`。在 README 补一行用法。
   目的：满足任务书"至少接通一种搜索"。

2. **self_check 加两项防回归**：
   - manifest 任一 `success=true` 条目若 `url=N/A`、`sha256=null`、`text_chars<=0`，判 FAIL。
   - 报告里所有"共核验 N 条判断"必须等于 `03_verification.json` 的 `total_claims`。

---

## 明确不做（留到 12 月）

- 不新增论文、真实招聘、科普来源
- 不把 S033–S042 深度整合进各方向主题页
- 不换 BM25/向量检索
- 不重写报告生成器、不做 `run_pipeline.py`
- 不做 config loader、不做通用领域改造
- 不改 registry 的 32 份真实来源，不改整理卡主体

## 红线

- 不编造 URL、时间、哈希、正文长度、核验结果。
- 覆盖任何文件前先备份；不删除旧报告。
- 岗位页没有真实招聘样本就保持"未找到"，不要把 `unverifiable` 包装成 `supported`。
- 网络失败就如实记录，不无限重试。
- 报告只改数字和重复章节，不改结论。

## 验收命令

```bash
cd "D:/新建文件夹/one/大三上/健康行业实践/general-domain-research-multi-agent-tool"

# 1. 自检（必须 8 项全 PASS）
python tools/self_check.py --run-id 261117-v2-final

# 2. 核验覆盖 13 页
python - <<'EOF'
import json
d=json.load(open('runs/261117-v2-final/03_verification.json',encoding='utf-8'))
print(d['total_claims'], d['pages_covered'], d['verdict_summary'])
assert d['pages_covered'] == 13
EOF

# 3. manifest 无占位成功项
python - <<'EOF'
import json
d=json.load(open('runs/261117-v2-final/01_fetch_manifest.json',encoding='utf-8'))
bad=[i['source_id'] for i in d['items'] if i.get('success') and (i.get('url') in (None,'N/A') or not i.get('sha256') or (i.get('text_chars') or 0)<=0)]
print('BAD:', bad)
assert not bad
EOF

# 4. 05_kb_update.md 存在
test -f runs/261117-v2-final/05_kb_update.md && echo OK

# 5. 旧数字清零
grep -nE "86 条|53 条 partially|28 份为 Wikipedia|指南（1 份|覆盖 9 个主题页" runs/261117-v2-final/04_report.md
# 期望无输出

# 6. 重复章节已合并（以下 8 个标题各只出现 1 次）
for h in "2.5 分歧与限制" "2.6 信息缺口" "3.5 分歧与限制" "3.6 信息缺口" "4.5 分歧与限制" "4.6 信息缺口" "5.5 分歧与限制" "5.6 信息缺口"; do
  n=$(grep -c "^### $h" runs/261117-v2-final/04_report.md)
  echo "$h -> $n"
done

# 7. role_log 无虚构工具，时间戳不全相同
grep -nE "fix_registry|generate_report|read_topic_pages|extract_findings" runs/261117-v2-final/role_log.jsonl
# 期望无输出
python - <<'EOF'
import json
ts=[json.loads(l)['timestamp'] for l in open('runs/261117-v2-final/role_log.jsonl',encoding='utf-8') if l.strip()]
print('unique timestamps:', len(set(ts)), '/', len(ts))
EOF

# 8. 旧报告已归档
grep -rn "基于真实招聘信息\|年薪25-40万\|8,000-12,000" output/*.md
# 期望无输出

# 9. 最终报告与 run 报告一致
sha256sum runs/261117-v2-final/04_report.md output/261117-v2-final_report.md
```

## 完成后请回报

1. 改了哪些文件（逐条）。
2. 重跑后的 `total_claims / pages_covered / verdict_summary`。
3. `01_fetch_manifest.json` 的 `fetched_in_this_run / reused` 值，以及 `status.json` 的 `web_fetches`。
4. 上述 9 条验收命令的实际输出。
5. 仍未解决或需要人工判断的问题，明确写"未解决"，不要略过。
