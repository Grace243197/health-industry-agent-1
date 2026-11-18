# V2 收口 · 分步执行 Prompt（2026-11-17）

## 使用方式

把本文件整份粘贴给千问 Desktop。

**它每次只执行一个步骤，完成后必须停下，等我回复"继续"再做下一步。**
没有收到"继续"，不得提前做后面的任务，不得把多个步骤合并执行。

## 总规则

1. 一次只做一个步骤。
2. 每步开始前先备份；每步结束后必须贴出：改了什么、跑了什么命令、实际输出、自检结果。
3. 任一步 FAIL、输出与预期不符、或遇到无法判断的内容，立即停下说明，不要带病继续。
4. 不改 registry 的 32 份真实来源；不改整理卡主体；不改 4 个岗位页的"未找到真实招聘样本"声明。
5. 所有时间用 `date -Iseconds` 记录。
6. 每完成一步，在 `runs/261117-v2-final/repair_log.md` 追加一节：时间、步骤、命令、实际输出、改动文件。该文件不存在就新建。
7. 项目根目录：

`D:\新建文件夹\one\大三上\健康行业实践\general-domain-research-multi-agent-tool`

每步回报模板：

```text
【步骤 X 完成】
时间：
改动文件：
执行命令：
实际输出：
自检：PASS / FAIL
下一步要做什么：
等待"继续"
```

---

## 步骤 0：备份与基线

只做备份和记录，不改任何业务文件。

1. 备份整个 run：

```bash
cp -r runs/261117-v2-final runs/261117-v2-final.bak-20261117
```

2. 记录基线：

```bash
export PYTHONIOENCODING=utf-8
python tools/self_check.py --run-id 261117-v2-final
python - <<'EOF'
import json
d=json.load(open('runs/261117-v2-final/03_verification.json',encoding='utf-8'))
print('verification:', d['total_claims'], d['pages_covered'], d['verdict_summary'])
m=json.load(open('runs/261117-v2-final/01_fetch_manifest.json',encoding='utf-8'))
bad=[i['source_id'] for i in m['items'] if i.get('success') and (i.get('url') in (None,'N/A') or not i.get('sha256') or (i.get('text_chars') or 0)<=0)]
print('manifest placeholder-success:', bad)
EOF
```

3. 新建 `runs/261117-v2-final/repair_log.md`，写入：

```markdown
# V2 收口修复日志

- 开始时间：<date -Iseconds>
- 基线：self_check 全部 PASS；verification 89 条 / 9 页；manifest 8 条占位成功
```

**停下，贴出基线输出，等待"继续"。**

---

## 步骤 1：修岗位页 claim 提取 bug，重跑核验

只改 verifier 和 4 个岗位页的核验状态，不改报告、不改 manifest。

1. 修改 `tools/evidence_verifier_v2.py` 约第 110–111 行。

原代码：

```python
section_match = re.search(rf'##.*{section_name}.*\n(.*?)(?=\n##\s|\Z)', content, re.DOTALL)
```

新代码：

```python
section_match = re.search(
    rf'^##[^\n]*{re.escape(section_name)}[^\n]*\n(.*?)(?=\n##[ \t]|\Z)',
    content, re.DOTALL | re.MULTILINE
)
```

2. 重跑核验：

```bash
python tools/evidence_verifier_v2.py --run-id 261117-v2-final
```

3. 打印结果：

```bash
python - <<'EOF'
import json
d=json.load(open('runs/261117-v2-final/03_verification.json',encoding='utf-8'))
print(d['total_claims'], d['pages_covered'], d['verdict_summary'])
print(sorted({r['page'] for r in d['results']}))
EOF
```

预期：

- `pages_covered` 从 9 变成 **13**
- `total_claims` 大于 89
- 4 个岗位页都出现在页面列表里
- 岗位页判断因无 `source_id` 被判 `unverifiable`，这是正确结果

4. 更新 4 个岗位页末尾的核验状态，把：

```markdown
- 待核验（岗位页尚未纳入 evidence_verifier_v2 覆盖范围）
```

改为：

```markdown
- 已纳入核验；因未找到真实招聘样本，岗位职责类判断标记为 unverifiable。
```

文件：

- `knowledge_base/topics/job_sleep_physician.md`
- `knowledge_base/topics/job_sleep_technologist.md`
- `knowledge_base/topics/job_sleep_center_admin.md`
- `knowledge_base/topics/job_sleep_health_educator.md`

红线：不给岗位页编造 `source_id`；不把 `unverifiable` 手工改成 `supported`。

**停下，贴出重跑结果，等待"继续"。**

---

## 步骤 2：跑知识库更新，补出 05_kb_update.md

只跑 `kb_updater.py`，不改报告。

1. 第一次运行：

```bash
python tools/kb_updater.py --run-id 261117-v2-final
```

2. 检查：

```bash
test -f runs/261117-v2-final/05_kb_update.md && echo "05 OK"
for f in knowledge_base/topics/*.md; do
  echo "$f -> $(grep -c '^## 核验状态' "$f")"
done
```

预期：每个主题页恰好 1 个 `## 核验状态`；`05_kb_update.md` 存在。

3. 再运行一次，验证幂等：

```bash
python tools/kb_updater.py --run-id 261117-v2-final
for f in knowledge_base/topics/*.md; do
  echo "$f -> $(grep -c '^## 核验状态' "$f")"
done
```

预期：仍然每个主题页恰好 1 个，没有重复段落。

**停下，贴出两次运行后的计数，等待"继续"。**

---

## 步骤 3：把抓取记录改成如实记录（不联网）

不重新抓取，不改原文，只改运行记录。

### 3.1 重写 `runs/261117-v2-final/01_fetch_manifest.json`

10 条统一按以下字段填写：

- `source_id`
- `url`：从 `knowledge_base/registry.jsonl` 的 `url_or_path` 读取，不得为 `N/A`
- `final_url`：从 `canonical_url` 读取
- `status`：S040、S042 保留 200；其余 8 条填 `null`
- `sha256`：`knowledge_base/sources/<SID>/raw.html` 的文件哈希
- `sha256_scope`: `"raw.html"`
- `text_chars`：`extracted.md` 的字符数，必须 > 0
- `elapsed`：S040、S042 保留原值；其余 8 条填 `null`
- `success`: `true`
- `timestamp`：`raw.html` 的 mtime，ISO 格式
- `timestamp_source`: `"file_mtime"`
- `fetched_in_this_run`: `false`
- `reused`: `true`
- `reused_from`：S040/S042 填 `"261117-v2-fix"`；其余 8 条填 `"prior_batch_2026-11-17T15:40-15:42"`
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

### 3.2 更新 `runs/261117-v2-final/status.json`

```json
"budget_used": {
  "sources_collected": 32,
  "web_fetches": 0,
  "reused_sources": 10,
  "supplement_rounds": 0
},
"note": "本次运行未重新联网抓取；10 份来源复用自已保存原件"
```

### 3.3 更新 `runs/261117-v2-final/01_collection.json`

```json
"tool_calls": [
  {"tool": "local_reuse", "action": "load S033-S042 from knowledge_base/sources", "count": 10},
  {"tool": "manual_registry_edit", "action": "标记 S027-S032 excluded、S013/S016/S018/S026 duplicate", "count": 10}
],
"new_fetched_note": "新入知识库 10 份；其中 2 份来自 261117-v2-fix，8 份来自 2026-11-17 15:40-15:42 批次；本次运行未重新抓取"
```

### 3.4 在 `knowledge_base/pending_sources.md` 末尾追加

```markdown
## 抓取日志缺口（建议下轮重抓）

- S033–S039、S041：原件存在，但缺少独立抓取日志（raw.html mtime 2026-11-17 15:40–15:42）。
- 建议下次联网时用 `fetch_sources.py --force` 重抓并生成完整 manifest。
```

### 3.5 自检

```bash
python - <<'EOF'
import json
d=json.load(open('runs/261117-v2-final/01_fetch_manifest.json',encoding='utf-8'))
bad=[i['source_id'] for i in d['items'] if i.get('success') and (i.get('url') in (None,'N/A') or not i.get('sha256') or (i.get('text_chars') or 0)<=0)]
print('BAD:', bad)
assert not bad
EOF
```

**停下，贴出 `BAD: []`，等待"继续"。**

---

## 步骤 4：重写 role_log.jsonl

只改 `runs/261117-v2-final/role_log.jsonl`。

1. 备份旧文件：

```bash
cp runs/261117-v2-final/role_log.jsonl runs/261117-v2-final/role_log.before_repair.jsonl
```

2. 重写规则：

- 只记录真实存在的工具和真实发生的动作。
- 禁止出现：`fix_registry.py`、`generate_report`、`read_topic_pages`、`extract_findings`。
- 历史五个阶段（collect / research / verify / curate / report）的时间用对应产物文件的 mtime，并加 `"timestamp_source": "file_mtime"`。
- 本次修复步骤（步骤 0–4）用真实时间，并加 `"timestamp_source": "runtime"`。
- 时间戳不能全部相同。

历史阶段字段建议：

```json
{"role":"source-collector","phase":"collect","run_id":"261117-v2-final","timestamp":"<01_collection.json 的 mtime ISO>","timestamp_source":"file_mtime","input_files":["knowledge_base/registry.jsonl"],"output_files":["runs/261117-v2-final/01_collection.json"],"tool_calls":[{"tool":"local_reuse","target":"S033-S042","count":10},{"tool":"manual_registry_edit","target":"registry.jsonl","count":10}],"status":"ok"}
```

```json
{"role":"topic-researcher","phase":"research","run_id":"261117-v2-final","timestamp":"<02_research 目录最早 mtime ISO>","timestamp_source":"file_mtime","input_files":["runs/261117-v2-final/01_collection.json","knowledge_base/topics/"],"output_files":["runs/261117-v2-final/02_research/RD.json","runs/261117-v2-final/02_research/CL.json","runs/261117-v2-final/02_research/AD.json","runs/261117-v2-final/02_research/PC.json"],"tool_calls":[{"tool":"llm_research","target":"4 directions"}],"status":"ok"}
```

```json
{"role":"evidence-verifier","phase":"verify","run_id":"261117-v2-final","timestamp":"<03_verification.json 的 mtime ISO>","timestamp_source":"file_mtime","input_files":["runs/261117-v2-final/02_research/*.json","knowledge_base/sources/"],"output_files":["runs/261117-v2-final/03_verification.json"],"tool_calls":[{"tool":"evidence_verifier_v2.py","target":"9 topic pages + 4 job pages","claims_extracted":<当前数字>}],"status":"ok"}
```

```json
{"role":"knowledge-curator","phase":"curate","run_id":"261117-v2-final","timestamp":"<05_kb_update.md 的 mtime ISO>","timestamp_source":"file_mtime","input_files":["runs/261117-v2-final/03_verification.json"],"output_files":["runs/261117-v2-final/05_kb_update.md","knowledge_base/topics/"],"tool_calls":[{"tool":"kb_updater.py","target":"9 topic pages"}],"status":"ok"}
```

```json
{"role":"report-writer","phase":"report","run_id":"261117-v2-final","timestamp":"<04_report.md 的 mtime ISO>","timestamp_source":"file_mtime","input_files":["runs/261117-v2-final/03_verification.json","knowledge_base/topics/"],"output_files":["runs/261117-v2-final/04_report.md","output/261117-v2-final_report.md"],"tool_calls":[{"tool":"manual_edit","target":"04_report.md"}],"status":"ok"}
```

3. 追加本次修复的 start/end 记录，用当前真实时间：

```json
{"role":"main","phase":"start","run_id":"261117-v2-final","timestamp":"<date -Iseconds>","timestamp_source":"runtime","note":"V2 收口修复开始"}
```

```json
{"role":"main","phase":"end","run_id":"261117-v2-final","timestamp":"<date -Iseconds>","timestamp_source":"runtime","note":"V2 收口修复完成"}
```

4. 自检：

```bash
grep -nE "fix_registry|generate_report|read_topic_pages|extract_findings" runs/261117-v2-final/role_log.jsonl
# 期望无输出
python - <<'EOF'
import json
ts=[json.loads(l)['timestamp'] for l in open('runs/261117-v2-final/role_log.jsonl',encoding='utf-8') if l.strip()]
print('unique timestamps:', len(set(ts)), '/', len(ts))
EOF
```

**停下，贴出 unique timestamps 和 grep 结果，等待"继续"。**

---

## 步骤 5：统一报告数字（先不去重）

只改数字和同步 output，不删重复章节。

1. 读取当前数字：

```bash
python - <<'EOF'
import json
d=json.load(open('runs/261117-v2-final/03_verification.json',encoding='utf-8'))
print('total_claims =', d['total_claims'])
print('pages_covered =', d['pages_covered'])
print('verdict_summary =', d['verdict_summary'])
EOF
```

2. 来源构成固定值：

- 32 份唯一真实来源
- 27 份 `popular`（均为 Wikipedia）
- 2 份 `meeting_note`
- 2 份 `guideline`：S039（NHS）、S041（WHO）
- 1 份 `institutional`：S038（ResMed）
- 证据等级：30 份 C 级，2 份 B 级（S039、S041）

3. 修改 `runs/261117-v2-final/04_report.md`，用 grep 定位：

| 原文本 | 改法 |
|---|---|
| `共核验 89 条判断，覆盖 9 个主题页` | 用 JSON 的 `total_claims`；覆盖改为 `13 个页面（9 个主题页 + 4 个岗位页）` |
| `核验 86 条判断中 5 条 supported、53 条 partially_supported、28 条 not_supported` | 用 JSON 数字 |
| `86 条核验判断：supported=5, partially_supported=53, not_supported=28, unverifiable=0` | 用 JSON 数字 |
| `Wikipedia 百科（28 份）` | `Wikipedia 百科（27 份）` |
| `指南（1 份，NHS）` | `指南（2 份：NHS、WHO）` |
| `28 份为 Wikipedia 百科条目` | `27 份为 Wikipedia 百科条目` |
| `1 份 NHS 指南（B 级）` | `2 份指南（NHS、WHO，B 级）` |
| `popular（Wikipedia 28 份）` | `popular（Wikipedia 27 份）`，同表补 `guideline（NHS、WHO 各 1 份）` |

4. 同步修改 `knowledge_base/topics/cross_direction_synthesis.md` 第 10、18 行同样的来源构成与核验数字。

5. 同步 output：

```bash
cp runs/261117-v2-final/04_report.md output/261117-v2-final_report.md
```

6. 自检：

```bash
grep -nE "86 条|53 条 partially|28 份为 Wikipedia|指南（1 份|覆盖 9 个主题页" runs/261117-v2-final/04_report.md
# 期望无输出
sha256sum runs/261117-v2-final/04_report.md output/261117-v2-final_report.md
# 期望哈希相同
```

**停下，贴出 grep 无输出和哈希一致，等待"继续"。**

---

## 步骤 6：删除重复章节

只处理报告里的 8 个重复标题，每个只保留一个：

- `### 2.5 分歧与限制`、`### 2.6 信息缺口`
- `### 3.5 分歧与限制`、`### 3.6 信息缺口`
- `### 4.5 分歧与限制`、`### 4.6 信息缺口`
- `### 5.5 分歧与限制`、`### 5.6 信息缺口`

做法：

1. 定位所有出现位置：

```bash
grep -nE "^### (2\.5|2\.6|3\.5|3\.6|4\.5|4\.6|5\.5|5\.6) " runs/261117-v2-final/04_report.md
```

2. 每一组保留第一次出现的段落；把第二次段落中不重复的要点合并进去；删除第二个标题及其整块。
3. 合并后每个标题只出现一次。
4. 不要动以下内容，它们是 4 个岗位页各自的子标题：
   - `### 2.1 临床诊疗`、`### 2.2 监测解读` 等
   - `### 3.1 教育背景`、`### 3.2 专业知识`、`### 3.3 技能要求`、`### 3.4 资质认证`
   - `### 4.1 数据来源说明`、`### 4.2 职业发展路径`、`### 4.3 工作场景`
   - 4 个 `## 一、岗位概述`
5. 如果无法判断某段是否重复，**停下来说明**，不要直接删。
6. 同步 output：

```bash
cp runs/261117-v2-final/04_report.md output/261117-v2-final_report.md
```

7. 自检：

```bash
for h in "2.5 分歧与限制" "2.6 信息缺口" "3.5 分歧与限制" "3.6 信息缺口" "4.5 分歧与限制" "4.6 信息缺口" "5.5 分歧与限制" "5.6 信息缺口"; do
  echo "$h -> $(grep -c "^### $h" runs/261117-v2-final/04_report.md)"
done
# 期望每个都是 1
```

**停下，贴出 8 个计数，等待"继续"。**

---

## 步骤 7：归档旧报告 + 最终验收

1. 归档旧报告：

```bash
mkdir -p output/archive
mv output/261117-v2-fix_report.md output/archive/
mv output/261117-v2-full_report.md output/archive/
mv output/v2_run1_report.md output/archive/
```

2. 更新 `docs/v1-changelog.md` 中引用这三个文件的路径为 `output/archive/...`。

3. 跑完整验收：

```bash
# 1. 自检
python tools/self_check.py --run-id 261117-v2-final

# 2. 核验覆盖
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

# 4. 05 存在
test -f runs/261117-v2-final/05_kb_update.md && echo OK

# 5. 旧数字清零
grep -nE "86 条|53 条 partially|28 份为 Wikipedia|指南（1 份|覆盖 9 个主题页" runs/261117-v2-final/04_report.md

# 6. 重复章节计数
for h in "2.5 分歧与限制" "2.6 信息缺口" "3.5 分歧与限制" "3.6 信息缺口" "4.5 分歧与限制" "4.6 信息缺口" "5.5 分歧与限制" "5.6 信息缺口"; do
  echo "$h -> $(grep -c "^### $h" runs/261117-v2-final/04_report.md)"
done

# 7. role_log
grep -nE "fix_registry|generate_report|read_topic_pages|extract_findings" runs/261117-v2-final/role_log.jsonl
python - <<'EOF'
import json
ts=[json.loads(l)['timestamp'] for l in open('runs/261117-v2-final/role_log.jsonl',encoding='utf-8') if l.strip()]
print('unique timestamps:', len(set(ts)), '/', len(ts))
EOF

# 8. 旧报告归档
grep -rn "基于真实招聘信息\|年薪25-40万\|8,000-12,000" output/*.md

# 9. 报告一致
sha256sum runs/261117-v2-final/04_report.md output/261117-v2-final_report.md
```

4. 在 `repair_log.md` 追加最终结果。

**停下，贴出 9 条验收命令的实际输出，等待我确认是否结束。**

---

## 可选步骤（只有我说"做可选步骤"才执行）

### 可选 A：Wikipedia 搜索适配器

新建 `tools/search_sources.py`：

- 调用 `https://en.wikipedia.org/w/api.php?action=query&list=search&srsearch=<query>&format=json`
- 支持 `--query`、`--limit`、`--run-id`
- 输出 `runs/<run_id>/search_results.json`，含标题、摘要、URL
- README 补一行用法

### 可选 B：self_check 防回归

给 `tools/self_check.py` 增加：

1. manifest 任一 `success=true` 条目若 `url=N/A`、`sha256=null`、`text_chars<=0`，判 FAIL。
2. 报告所有"共核验 N 条判断"必须等于 `03_verification.json` 的 `total_claims`。

---

## 明确不做

- 不新增论文、真实招聘、科普来源
- 不把 S033–S042 深度整合进各方向
- 不换 BM25/向量检索
- 不重写报告生成器、不做 `run_pipeline.py`
- 不做 config loader、不做通用领域改造
- 不改 registry 的 32 份真实来源
- 不改整理卡主体

## 红线

- 不编造 URL、时间、哈希、正文长度、核验结果。
- 覆盖任何文件前先备份；不删除旧报告。
- 岗位页没有真实招聘样本就保持"未找到"，不要把 `unverifiable` 包装成 `supported`。
- 报告只改数字和重复章节，不改结论。
- 任一步不确定就停下，不要猜。
