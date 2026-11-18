# 给千问 Desktop 的 v2-final 修复 Prompt（2026-11-17）

你是本项目的执行智能体。项目根目录：

`D:\新建文件夹\one\大三上\健康行业实践\general-domain-research-multi-agent-tool`

## 先读

1. `docs/v2-gap-report.md`（验收标准）
2. `sleep-health-student-project-guide.md`（任务书）
3. `RUNBOOK.md`、`config/project.json`
4. `runs/261117-v2-final/` 下全部产物

## 背景

`261117-v2-final` 已通过 `self_check.py --run-id 261117-v2-final` 的 8 项检查，但人工复核发现 4 类问题。按下面顺序修，**先修核验工具，再统一报告数字**，否则数字会再次过期。

---

## 任务 0：备份

1. 复制 `runs/261117-v2-final/` 到 `runs/261117-v2-final.bak-20261117/`。
2. 重抓前，把 `knowledge_base/sources/S033`–`S041` 的 `raw.html`、`extracted.md` 归档到各自目录下的 `archive_20261117/`。
3. 不删除任何旧文件。

## 任务 1：修复岗位页 claim 提取 bug（P0，先做）

**文件**：`tools/evidence_verifier_v2.py:110-111`

**问题**：岗位页兜底提取用了

```python
section_match = re.search(rf'##.*{section_name}.*\n(.*?)(?=\n##\s|\Z)', content, re.DOTALL)
```

`re.DOTALL` 让 `.*` 可以跨行，匹配会一路吞到文件末尾，`group(1)` 为空，所以 4 个岗位页都提取出 0 条 claim，`pages_covered` 只有 9。

**修复**：

```python
section_match = re.search(
    rf'^##[^\n]*{re.escape(section_name)}[^\n]*\n(.*?)(?=\n##[ \t]|\Z)',
    content, re.DOTALL | re.MULTILINE
)
```

修复后运行：

```bash
python tools/evidence_verifier_v2.py --run-id 261117-v2-final
```

预期：`pages_covered=13`（9 个主题页 + 4 个岗位页），`total_claims` 增加，4 个岗位页的判断因没有 `source_id` 被判 `unverifiable`。

**红线**：

- 不要为了好看给岗位页编造 `source_id`，也不要手工把 `unverifiable` 改判为 `supported`。
- 如果岗位页提取出的条目过多（例如超过 40 条/页），可以在提取时只保留 `- ` 开头且长度 > 20 的行，但必须保留 4 个页面各有 claim。
- 更新 4 个岗位页末尾的核验状态（`job_sleep_physician.md:115`、`job_sleep_technologist.md:112`、`job_sleep_center_admin.md:127`、`job_sleep_health_educator.md:134`），把"岗位页尚未纳入 evidence_verifier_v2 覆盖范围"改为："已纳入核验；因未找到真实招聘样本，岗位职责类判断标记为 unverifiable。"

## 任务 2：修复抓取记录（P0）

**问题**：`runs/261117-v2-final/01_fetch_manifest.json` 共 10 条，只有 S040、S042 有真实 URL/sha256/15:55 时间戳；S033–S039、S041 共 8 条是 `url=N/A`、`text_chars=0`、`timestamp=17:12` 的占位，备注"从 v2-fix 运行继承"，但 `runs/261117-v2-fix/01_fetch_manifest.json` 只有 S040、S042 两条。这 8 份原件实际存在（`raw.html` mtime 15:40–15:42），但没有抓取日志。`status.json` 的 `web_fetches=10` 与事实不符。

**优先方案（网络可用时）**：

1. 给 `tools/fetch_sources.py` 增加 `--force` 参数：当传入 `--force --source-ids ...` 时，不再要求 `fetch_status=pending`，对指定来源强制重抓。
2. 归档旧原件后执行：

```bash
python tools/fetch_sources.py --fetch --force --run-id 261117-v2-refetch \
  --source-ids S033 S034 S035 S036 S037 S038 S039 S041
```

3. 把 `runs/261117-v2-refetch/01_fetch_manifest.json` 中的 8 条合并进 `runs/261117-v2-final/01_fetch_manifest.json`。每条必须含：
   - `source_id`
   - `url`（实际请求 URL，不得为 N/A）
   - `final_url`
   - `status`（HTTP 状态码）
   - `sha256`（HTTP 响应体哈希）
   - `raw_sha256`（保存到 `raw.html` 后的文件哈希）
   - `elapsed`
   - `success`
   - `text_chars`（`extracted.md` 正文长度，必须 > 0）
   - `timestamp`（真实抓取时间，ISO 格式）
   - `fetched_in_this_run`: `true`
   - `reused`: `false`
4. S040、S042 保留 15:55 的原始抓取记录，并标 `fetched_in_this_run: false`、`reused: true`、`reused_from: "261117-v2-fix"`。
5. 更新 `status.json`：按实际填写 `web_fetches`（预期 8）、`reused_sources`（预期 2）、`sources_collected: 32`。
6. 更新 `01_collection.json` 的 `tool_calls`，如实区分"重抓 8 条"和"复用 2 条"；`new_fetched` 可保留 S033–S042，但需说明是"新入知识库"，不是"本次全部重新抓取"。

**兜底方案（网络不可用）**：

不要伪造抓取成功。改为如实记录复用：

- 8 条的 `url` 从 registry 的 `url_or_path` 读取，`final_url` 用 `canonical_url`；
- `sha256` 用 `raw.html` 文件哈希，`text_chars` 用 `extracted.md` 正文长度；
- `timestamp` 用 `raw.html` 的 mtime，并增加 `timestamp_source: "file_mtime"`；
- 增加 `reused: true`、`fetched_in_this_run: false`、`note: "本次运行未重新抓取；复用 2026-11-17 15:40–15:42 已保存原件，无独立抓取日志"`；
- `status.json` 写 `web_fetches: 0`、`reused_sources: 10`；
- 在 `knowledge_base/pending_sources.md` 记录"以下 8 份缺少独立抓取日志，建议下轮重抓：S033–S039、S041"。

无论走哪条路径，**manifest 中不允许出现 `success=true` 但 `url=N/A`、`sha256=null` 或 `text_chars=0` 的条目。**

## 任务 3：统一报告与主题页数字（P0，必须在任务 1 之后）

来源构成的正确数字（来自 `knowledge_base/registry.jsonl`，32 份唯一真实来源）：

- 27 份 `popular`（均为 Wikipedia）
- 2 份 `meeting_note`
- 2 份 `guideline`：S039（NHS）、S041（WHO）
- 1 份 `institutional`：S038（ResMed）
- 证据等级：30 份 C 级，2 份 B 级（S039、S041）

核验数字**不要硬编码**，一律从 `runs/261117-v2-final/03_verification.json` 读取 `total_claims`、`pages_covered`、`verdict_summary`。

需要修改的位置：

1. `runs/261117-v2-final/04_report.md:840`：来源构成（28→27；指南 1 份→2 份，NHS/WHO）。
2. `runs/261117-v2-final/04_report.md:842`：旧的"86 条 / 5 supported / 53 partially / 28 not_supported"改为当前 JSON 数字。
3. `runs/261117-v2-final/04_report.md:848`：28 份 Wikipedia→27；"1 份 NHS 指南"→"2 份指南（NHS、WHO，B 级）"。
4. `runs/261117-v2-final/04_report.md:849`：86/5/53/28 改为当前 JSON 数字（含 `unverifiable`）。
5. `runs/261117-v2-final/04_report.md:975`：Wikipedia 28→27，并补上 guideline（S041 WHO）。
6. `runs/261117-v2-final/04_report.md:42` 和 `:914`："覆盖 9 个主题页"→"覆盖 13 个页面（9 个主题页 + 4 个岗位页）"。
7. `knowledge_base/topics/cross_direction_synthesis.md:10` 和 `:18`：同步同样的来源构成与核验数字。

改完后用 `cp` 让 `output/261117-v2-final_report.md` 与 `runs/261117-v2-final/04_report.md` 逐字节一致。

**禁止**：只改一处、留下其它旧数字；禁止改结论、增删来源或改写判断。

## 任务 4：处理 output 目录中的旧报告（P1）

以下文件仍含"基于真实招聘信息"和模拟薪资，若验收 grep 整个 `output/` 会命中：

- `output/261117-v2-fix_report.md`（第 397、525 行"基于真实招聘信息"；第 403、531 行薪资）
- `output/261117-v2-full_report.md`（第 222、234 行薪资）
- `output/v2_run1_report.md`（第 222、234 行薪资）

处理方式（二选一，优先方案 A）：

- **A**：新建 `output/archive/`，把这三个文件移进去；更新 `docs/v1-changelog.md:117,170` 中的路径为 `output/archive/...`。
- **B**：在原文件开头加醒目声明：

```markdown
> **历史版本，禁止作为最终交付**：本报告包含已排除的模拟材料 S027–S032 及模拟薪资，仅用于版本追溯。最终报告见 `output/261117-v2-final_report.md`。
```

不删除文件。

## 任务 5：给 self_check 增加防回归检查（P1）

修改 `tools/self_check.py`，增加：

1. **manifest 真实性**：读取 `runs/<run_id>/01_fetch_manifest.json`，任一 `success=true` 的条目若 `url` 为 `N/A`、`sha256` 为 `null`、或 `text_chars <= 0`，判 `fetch_manifest_integrity=FAIL`。
2. **报告数字一致性**：从 `03_verification.json` 读取 `total_claims`、`pages_covered`；在 `04_report.md` 中查找所有"共核验 N 条判断"和"覆盖 N 个"表述，若与 JSON 不一致，判 `report_numbers_consistent=FAIL`。

运行：

```bash
python tools/self_check.py --run-id 261117-v2-final
```

必须全部 PASS（含新增检查）。

## 验收命令

```bash
cd "D:/新建文件夹/one/大三上/健康行业实践/general-domain-research-multi-agent-tool"

# 1. 自检
python tools/self_check.py --run-id 261117-v2-final

# 2. 核验覆盖
python -c "import json;d=json.load(open('runs/261117-v2-final/03_verification.json',encoding='utf-8'));print(d['total_claims'],d['pages_covered'],d['verdict_summary'])"
# 期望 pages_covered == 13

# 3. manifest 无占位成功项
python -c "import json;d=json.load(open('runs/261117-v2-final/01_fetch_manifest.json',encoding='utf-8'));bad=[i['source_id'] for i in d['items'] if i.get('success') and (i.get('url') in (None,'N/A') or not i.get('sha256') or (i.get('text_chars') or 0)<=0)];print('BAD:',bad)"
# 期望 BAD: []

# 4. 旧数字清零（最终报告）
grep -nE "86 条|53 条 partially|28 份为 Wikipedia|指南（1 份" runs/261117-v2-final/04_report.md
# 期望无输出

# 5. 旧报告不再污染 output/
grep -rn "基于真实招聘信息\|年薪25-40万\|8,000-12,000" output/*.md
# 期望无输出

# 6. 最终报告与 run 报告一致
sha256sum runs/261117-v2-final/04_report.md output/261117-v2-final_report.md
# 期望哈希相同
```

## 红线

- 不编造 URL、时间、哈希、正文长度、核验结果。
- 重抓失败就写 `knowledge_base/pending_sources.md`，保留旧原件与缺口，不无限重试。
- 覆盖任何原件前先归档；不删除旧报告。
- 岗位页没有真实招聘样本就如实写"未找到"，不要把 `unverifiable` 包装成 `supported`。
- 不改报告结论，只做数字与记录一致性修复。

## 完成后请回报

1. 改了哪些文件（逐条）。
2. 任务 1 重跑后的 `total_claims / pages_covered / verdict_summary`。
3. manifest 中 S033–S041 是重抓还是复用，`web_fetches` 最终值。
4. 上述 6 条验收命令的实际输出。
5. 仍未解决的缺口（如有），明确写"未解决"，不要略过。
