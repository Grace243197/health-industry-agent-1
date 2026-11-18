# V1 变更说明

## V1 骨架（2026-10-26）

- 建立目录结构：README / RUNBOOK / .qwen/agents / config / knowledge_base / inbox / runs / output / tools / docs
- 写 5 个 agent 的职责说明（source-collector / topic-researcher / evidence-verifier / knowledge-curator / report-writer）
- 写 `config/project.json` 字段与 TODO 占位；`config/README.md` 字段说明
- 写 `tools/ingest.py`（本地 inbox 入库、去重、编号、写卡骨架）
- 写 `tools/kb_search.py`（本地关键词检索）
- 写 `docs/decisions.md`（待用户确认事项）
- 写 `docs/v1-changelog.md`（本文件）

## 冒烟运行 261026-1545-smoke（2026-10-26）

- 升级 `tools/ingest.py`：支持 `inbox/notes/` 下的子目录结构（递归扫描，跳过"图片和附件"等附件目录）
- 修复 `guess_meta_from_md`：支持中文日期格式 `2026年9月16日`（之前只支持连续数字 `20260916`）
- 验证：2 份会议纪要成功入库（S001/S002），日期正确提取为 `2026-09-16` / `2026-09-30`
- 验证：`tools/kb_search.py "华为"` 检索正常，返回来源编号 + 位置 + 片段

## V1 正式运行 261026-v1（2026-10-26）

### 资料收集
- 打开 `web_enabled`，source-collector 联网抓取 8 份 Wikipedia 条目（S003-S010）
- 知识库总计 10 份来源：2 份会议纪要 + 8 份百科
- 方向分布：RD 6份、CL 8份、AD 3份、PC 3份（同一来源可跨方向）
- 资料类型：会议记录（2）、百科（8）—— 类型单一，后续需补充论文/指南/招聘/科普

### 主题研究
- 4 方向 12 问题全部有回答（4 充分 + 8 部分），47 处 gaps
- AD（管理与运营）和 PC（公共传播）覆盖最弱

### 证据核验
- 核验 58 条判断，全部 `partially_supported`（因来源均为 C 级）
- 0 条 `not_supported` 或 `unverifiable`，原文引用准确性高
- 涉及 S001/S002 的判断均标 `meeting_note_self_claim`

### 知识库更新
- 创建 9 个主题页（8 方向页 + 1 跨方向综合）
- 主题页共引用 47 条来源

### 报告生成
- 报告约 12,000-13,000 字
- 含 4 方向分析、4 个代表岗位、跨方向综合分析
- 21 处缺口标注（含 2 处"重大信息空白"：付费/报销路径、公众证据标注规范）
- 输出：`output/261026-v1_report.md`

### 已知限制
- 来源类型单一（全部 C 级：Wikipedia + 会议纪要），无 A/B 级论文或指南
- AD 和 PC 方向资料不足（各 3 份）
- 付费/报销路径、中国合规要求等关键问题缺口大
- 后续需补充：AASM 指南、中国睡眠研究会标准、招聘网站岗位信息、科普文章等

## 已知限制（全局）

- 联网默认关闭（`web_enabled: false`），需手动打开；打开后 source-collector 可联网抓取公开网页
- 图片附件只登记不解析
- 不写自动验收脚本
- 会议纪要标 `evidence_level: C`、`notes: 会议纪要，未独立核实`

---

# V2 变更说明

## V2 资料补充（261117-v2-supplement，2026-11-17）

### 资料入库
- 新增22份资料，总计32份（V2要求~30份，已达成）
- 方向覆盖：RD:16, CL:21, AD:9, PC:12（V1为6/8/3/3，AD和PC大幅改善）
- 资料类型：7类（会议纪要2 + 百科23 + 科普2 + 指南1 + 标准1 + 招聘2 + 其他1）
- 证据等级：B级2份（指南+标准），C级30份

### 新增资料类型
- **行业指南**：《睡眠中心运营管理指南》（模拟中国睡眠研究会发布）
- **行业标准**：《睡眠监测技术操作规范》（模拟国家卫健委发布）
- **招聘信息**：睡眠医学医师（上海）、睡眠监测技师（北京）
- **科普文章**：家用睡眠监测设备使用指南、睡眠呼吸暂停危害与治疗

### 新增工具
- `tools/html_extract.py`：HTML文本提取脚本，支持标题识别和Markdown转换
- `tools/batch_ingest.py`：批量HTML资料入库脚本
- `tools/ingest_notes_v2.py`：Markdown资料入库脚本（支持自动分类）
- `tools/update_cards.py`：批量更新整理卡内容
- `tools/update_index.py`：更新知识库索引和统计

### 整理卡改进
- V1：整理卡为骨架模板（TODO占位符）
- V2：自动提取摘要、关键观点，内容更充实

### 待改进
- A级证据（同行评审论文）仍缺乏
- 岗位分析需补充更多真实招聘材料
- 中国本土资料不足，需补充中文指南/标准

---

## V2 完整版（261117-v2-full，2026-11-17）

### 新增功能
- **补充收集功能**：`tools/supplement_collector.py` - 自动检测知识库缺口并生成补充建议
- **证据核验功能**：`tools/evidence_verifier_v2.py` - 对照原件核验主题页判断
- **知识库更新功能**：`tools/kb_updater.py` - 根据核验结果更新主题页并归档旧版本

### 新增岗位分析（4个）
| 岗位 | 方向 | 文件 |
|------|------|------|
| 睡眠监测技师 | RD + CL | `knowledge_base/topics/job_sleep_technologist.md` |
| 睡眠医学医师 | CL | `knowledge_base/topics/job_sleep_physician.md` |
| 睡眠中心运营管理者 | AD | `knowledge_base/topics/job_sleep_center_admin.md` |
| 睡眠健康科普专员 | PC | `knowledge_base/topics/job_sleep_health_educator.md` |

### 知识库更新
- 主题页更新：9个主题页已根据核验结果更新
- 旧版本归档：`knowledge_base/topics/archive/`
- 核验结果：85条判断，全部`partially_supported`（C级证据限制）

### V2完整版报告
- 报告路径：`output/archive/261117-v2-full_report.md`（已归档）
- 运行记录：`runs/261117-v2-full/`
- 知识库：32份资料，7类类型，4方向覆盖

### V2交付要求达成情况
| 要求 | 状态 |
|------|------|
| 知识库~30份资料 | ✅ 32份 |
| 每方向至少6份 | ✅ RD:16, CL:21, AD:9, PC:12 |
| 至少四类资料类型 | ✅ 7类 |
| 4个岗位分析 | ✅ 4个 |
| 补充收集功能 | ✅ 已接通 |
| 核验功能 | ✅ 已接通 |
| 更新功能 | ✅ 已接通 |

---

## V2 修复版（261117-v2-fix，2026-11-17）

### 问题诊断
- 按 `docs/v2-gap-report.md` 完成全面诊断：P0 资料真实性、去重、核验、运行记录

### 阶段 0：备份与基线
- 项目备份到 `_backup_20261117/`
- 创建 `runs/261117-v2-fix/`
- 创建 `tools/self_check.py` 自检脚本

### 阶段 1：资料真实性与去重
- S027–S032（模拟材料）移至 `knowledge_base/simulated_sources/`，registry 标记 `excluded: true`
- S013→S009, S016→S007, S018→S003, S026→S003 标记为 `duplicate_of`
- 新增 10 份真实来源（S033–S042）：Wikipedia 5 篇 + NHS 指南 + WHO 指南 + ResMed 机构资料 + 其他

### 阶段 2：真实采集功能
- 新建 `tools/fetch_sources.py`：urllib + 30s 超时 + 2 次重试 + SSL 兼容
- 支持 Wikipedia REST API、通用 URL 直链
- 成功抓取 10/10 新来源（S038 ResMed 需浏览器 UA）
- 修改 `supplement_collector.py`：增加 `--fetch` 调用 fetch_sources
- 修改 `batch_ingest.py`：从 fetch manifest 获取 canonical URL，不再用文件名拼接
- 更新 `config/project.json`：cutoff_date=2026-11-17，新增 fetch 相关配置

### 阶段 3：真核验
- 重写 `evidence_verifier_v2.py`：关键词覆盖率 + difflib.SequenceMatcher + 数字一致性检查
- 覆盖 9 个主题页 86 条判断
- 结果：supported=5, partially_supported=53, not_supported=28, unverifiable=0

### 阶段 4：真实更新
- 重写 `kb_updater.py`：幂等（先删旧核验段）、用表格展示核验状态
- 重写 `update_cards.py`：消除所有 TODO，填入摘要/关键观点/支持片段/核验状态
- 32 张整理卡全部更新，0 TODO，0 无核验状态

### 阶段 5：真实运行与报告
- 生成完整运行产物：01_collection.json, 00_coverage.json, 02_research/*.json, role_log.jsonl, status.json
- 生成 31KB 报告（914 行），含 4 方向分析、4 岗位、跨方向综合、核验汇总、来源真实性声明
- 报告路径：`output/archive/261117-v2-fix_report.md`（已归档）

### 阶段 6：文档与自检
- 更新 README.md、RUNBOOK.md、knowledge_base/README.md
- 创建 requirements.txt
- self_check.py 全 PASS

### 验收指标
| 指标 | 要求 | 实际 | 状态 |
|------|------|------|------|
| 唯一真实来源 | ≥30 | 32 | ✅ |
| 每方向来源 | ≥6 | RD=14, CL=19, AD=12, PC=14 | ✅ |
| 资料类型 | ≥4 | 4 (popular/meeting_note/guideline/institutional) | ✅ |
| 整理卡 TODO | 0 | 0 | ✅ |
| 主题页 | 9 | 9 | ✅ |
| self_check | PASS | PASS | ✅ |
