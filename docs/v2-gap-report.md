# V2 差距报告与修复计划（2026-11-17）

> 结论：当前是“名义 V2、实质未达标”。按任务书 2026-11-18 的 V2 要求，最优先修复资料真实性、核验与运行记录。

## 1. 对照表

| V2 要求 | 现状 | 判定 |
|---|---|---|
| 知识库约 30 份资料 | 登记 32 份；去重、去模拟后唯一真实约 22 份；AD 方向仅约 4 份 | 不达标 |
| 完善四方向分析 + 4 个岗位 | 9 个主题页、4 个岗位页、报告章节齐全；AD/PC 与岗位主要依赖 S029–S032 模拟材料 | 形式达标、内容存疑 |
| 接通补充收集 | `supplement_collector.py` 只输出搜索词，不抓取、不入库 | 未接通 |
| 接通核验 | `evidence_verifier_v2.py` 只按证据等级判定，不比对原文；85 条只覆盖 S001–S010 | 未真正核验 |
| 接通更新 | `kb_updater.py` 只追加 HTML 注释，不修订知识内容；重复运行产生重复段落 | 仅形式接通 |
| 第二版工具/知识库/报告/更新示例/变更说明 | 工具与报告在；README 仍 V1、RUNBOOK 未提 V2 工具；运行记录缺失且互相矛盾 | 不完整 |

## 2. 已确认问题

### P0 资料真实性
- `S027`–`S032` 原文末尾明确写着“模拟招聘信息 / 模拟行业指南 / 模拟行业标准 / 模拟科普文章”，但报告和岗位页把它们当真实机构材料引用，`S029/S030` 还标成 B 级。
- 报告与主题页没有任何“模拟材料”声明；岗位页甚至写“基于真实招聘信息”。
- 违反任务书“只使用公开或已获授权的资料”“引用真实招聘或机构材料”。

### P0 去重与规模
- `S003/S018/S026` 是同一篇 Polysomnography；`S007/S016` 是同一篇 ICSD；`S009/S013` 是同一篇 Positive Airway Pressure。
- 名义 32 份，唯一真实约 22 份；AD 方向唯一真实约 4 份，低于每方向 6 份的要求。
- `batch_ingest.py` 用文件名拼 Wikipedia URL，`S024/S025` 的 registry URL 与 raw.html 中的 canonical URL 不一致。

### P0 核验
- `tools/evidence_verifier_v2.py:89-131` 只检查来源是否存在、证据等级是否为 C，所有 C 级判断机械地判为 `partially_supported`。
- 85 条判断的来源统计只有 `S001–S010`；`S011–S032` 和 4 个岗位页完全没有被核验。
- 每条结果没有原文片段、没有位置、没有数字/实体一致性检查。

### P0 补充采集
- `tools/supplement_collector.py:103-186` 只生成搜索建议并写 JSON，不搜索、不抓取、不入库。
- `html_extract.py` 明确“不联网”；`batch_ingest.py` 只处理本地 `inbox/temp_*.html`。
- 仓库中没有实际抓取代码；`status.json` 的 `web_fetches: 15` 没有日志可追溯。
- `261117-v2-full` 的补充分析只识别出 A 级证据缺口，`search_queries` 为空，说明 22 份新增资料不是该功能跑出来的。

### P1 更新
- `tools/kb_updater.py:41-74` 只追加 `<!-- 核验: ... -->` 注释和“最后更新”行，不修改知识内容。
- 重复运行会重复追加“核验备注”；主题页顶部 `<!-- 原始更新记录...` 未闭合，正文被 Markdown 隐藏。

### P0 运行记录
- `runs/261117-v2-full/` 只有 `03_verification`、`04_report`、`05_kb_update`、`status`、`supplement_analysis`；缺 `00_coverage`、`01_collection`、`02_research`、`role_log`。
- `runs/v2_run1/` 缺 `02_research`；`role_log` 却声称 topic-researcher 已完成。
- `output/v2_run1_report.md` 与 `output/261117-v2-full_report.md` 逐字节相同，连报告头 `run_id: 261117-v2-full` 都没改。
- `runs/261117-v2-supplement/01_collection.json` 说新增 S022–S025，`01_collection_notes.json` 却说新增 S026–S032。

### P1 文档与卡片
- README 仍写“V1 骨架”；RUNBOOK 没提 `supplement_collector`、`evidence_verifier_v2`、`kb_updater`；`config/project.json` 的 `cutoff_date` 仍是 2026-10-26。
- `knowledge_base/README.md` 更新记录里有 `{date}` 占位符。
- 22/32 张整理卡仍有 `TODO`；0 张有“核验状态”；支持片段与原文位置普遍为空。
- 报告 12.5KB，比 V1 的 28KB 更短；一边说“缺乏中国睡眠研究会指南”，一边引用 S029 的“中国睡眠研究会指南”。

## 3. 修复顺序

### 阶段 0：备份与基线
- 复制项目到 `_backup_20261117/` 或建 git 分支。
- 新建 `runs/261117-v2-fix/`，后续产物写这里，不改旧 run。
- 新建 `tools/self_check.py`，先跑一次记录基线。

### 阶段 1：资料真实性与去重（P0）
- 把 `S027–S032` 移到 `knowledge_base/simulated_sources/`；从 registry 移除，或标 `excluded: true, type: simulated_material`；不计入统计，不再当真实来源引用。
- 重复组保留 extracted 最完整的一份，其余标 `duplicate_of: Sxxx`，不计入唯一数。
- 新增真实来源，使唯一真实 ≥30：
  - 论文/专业资料：PubMed E-utilities / PMC；只有摘要的标 `only_abstract: true`。
  - 指南/标准：AASM、NICE、NHS、WHO、国家卫健委、中国睡眠研究会官网，保存真实页面/PDF。
  - 机构/企业资料：官方报告、白皮书、医院公开材料。
  - 招聘：医院官网“人才招聘”、人社局/卫健委公开招聘公告，记录真实 URL、地区、发布日期。
  - 科普：官方或正规媒体公开文章。
- registry 必填：`source_id, title, type, publisher, publish_date, ingest_date, url_or_path, canonical_url, domain, theme, topics, access, evidence_level, raw_path, extracted_path, card_path, dedup_key, fetch_status`。不确定写 `unknown`。

### 阶段 2：真实采集功能（P0）
- 新建 `tools/fetch_sources.py`：读 `tools/source_plan.json`；支持 `--dry-run/--fetch/--run-id`；`urllib` + 30s 超时 + 2 次重试 + User-Agent；成功保存 `inbox/temp_<id>.html` 或 `inbox/pdfs/<id>.pdf`，失败写 `pending_sources.md`；记录 HTTP 状态、最终 URL、sha256、时间到 `01_fetch_manifest.json`。
- Wikipedia 用 `https://en.wikipedia.org/api/rest_v1/page/html/<Title>`；PubMed 用 esearch/efetch；Crossref/OpenAlex 用公开 API。
- 修改 `supplement_collector.py`：增加 `--fetch`，按缺口调用 `fetch_sources`，再调 `batch_ingest`；`--dry-run` 只出计划。
- 修改 `batch_ingest.py`：URL 从 fetch manifest 读取 canonical URL，不再用文件名拼接。
- 更新 `config/project.json`：`cutoff_date=2026-11-17`；增加 `source_plan_path`、`max_fetches`、`fetch_timeout_seconds`、`max_retries`。

### 阶段 3：真核验（P0）
- 重写 `evidence_verifier_v2.py`：从主题页“关键认识”和 4 个岗位页提取 claims；对每个 source 读取 extracted.md，按段落/句子切分，用关键词覆盖率 + `difflib.SequenceMatcher` 找最佳匹配，并检查数字/单位/实体一致性。
- 判定：`supported`（≥70% 关键词且数字/实体一致）、`partially_supported`（≥40% 或缺数字/实体，或仅摘要）、`not_supported`（明确矛盾/数字不符/匹配<20%）、`unverifiable`（来源缺失/不可读/仅链接）。
- 每条结果必须含 `excerpt`、`location`（段落号+字符偏移；PDF 页码）、`score`、`reason`、`flags`。
- 严禁只按 `evidence_level` 判定；覆盖全部 9 个主题页 + 4 个岗位页。

### 阶段 4：真实更新（P1）
- 重写 `kb_updater.py`：幂等（先删除旧“核验备注/核验状态”段）；用 `## 核验状态` 表格或 YAML frontmatter；不写未闭合 `<!--`；只把 supported/partially_supported 写入“关键认识”，not_supported/unverifiable 写入“分歧与限制/待解决”；归档旧版并记录 diff。
- 修复所有主题页的未闭合注释；删除重复核验段。
- 修 `update_cards.py`：填满摘要、关键观点、支持片段+位置、范围/限制、`verification_status`；0 TODO。S001/S002 标“AI生成会议纪要，未独立核实”。

### 阶段 5：真实运行与报告（P0）
- 用 `261117-v2-fix` 完整跑：collect → fetch/ingest → research → verify → curate → report。
- 生成 `02_research/RD|CL|AD|PC.json`（每条含 question/finding/source_ids/locations/excerpts/gaps）、`00_coverage.json`、`role_log.jsonl`、`status.json`。
- 报告只从 `03_verification` + topics 生成；禁止复制旧报告；必须有 4 方向、4 岗位、跨方向综合、引用（[Sxxx]+位置）、信息缺口、核验汇总、来源真实性声明/模拟材料清单；不得比 V1 更短、更空。

### 阶段 6：文档与自检（P1）
- 更新 README、RUNBOOK、`knowledge_base/README.md`、`docs/v1-changelog.md`：入口、阶段、交接、人工点、更新步骤、停止条件、结果位置、搜索替代方案、已知限制、模拟材料处理说明。
- 新建 `requirements.txt`（`pypdf`；可选 `requests`）。
- 新建 `tools/self_check.py` 并跑通：registry 必填字段/路径、唯一真实数、每方向数、类型数、cards 0 TODO、9 主题页、注释闭合、run 产物齐全、报告引用可追溯。
- 每阶段自检 FAIL 就停下说明，不带病继续。

## 4. 搜索替代方案

- 首选：固定 URL 清单 + 直链抓取，不依赖搜索。
- 次选：Wikipedia REST API、PubMed E-utilities、Crossref/OpenAlex 等结构化 API。
- 兜底：人工用浏览器保存 HTML/PDF 到 `inbox/`，再由 `batch_ingest` 入库；这是任务书允许的“人工导入资料”。
- 通用搜索只用于发现候选 URL；任何来源必须实际抓取并保存全文，才能计数。
- 抓不到就写 `pending_sources.md`，并在报告“信息缺口”中保留；不要用模拟材料补位。

## 5. 验收标准

- 唯一真实来源 ≥30；每方向 ≥6；类型 ≥4。
- 4 个岗位各至少 1 份真实招聘/机构材料，注明地区与日期；找不到就明确写“未找到真实招聘样本”。
- 9 个主题页齐全，无未闭合注释、无重复核验段，有来源引用/分歧/待解决。
- 所有整理卡无 TODO，含支持片段+原文位置、核验状态。
- 运行产物齐全；报告不是旧报告复制；引用可追溯到 registry。
- `self_check.py` 全 PASS。
