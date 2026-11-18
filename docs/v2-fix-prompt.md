# 给千问 Desktop 的 V2 修复 Prompt（精简版）

你是本项目的执行智能体。项目根目录：

`D:\新建文件夹\one\大三上\健康行业实践\general-domain-research-multi-agent-tool`

## 先读

1. `docs/v2-gap-report.md`（问题清单、验收标准、修复顺序）
2. `sleep-health-student-project-guide.md`（任务书）
3. `README.md`、`RUNBOOK.md`、`config/project.json`

## 任务

按 `docs/v2-gap-report.md` 的“修复顺序”从阶段 0 做到阶段 6，不要跳步。每阶段完成后：

- 运行 `python tools/self_check.py`（没有就先创建）
- 贴出 PASS/FAIL、改了哪些文件、唯一真实来源数变化
- 如果 FAIL，或需要删除/覆盖文件，停下说明，不要带病继续

## 红线

- 不编造来源、日期、URL、PMID/DOI、薪资、政策数字
- 不把模拟材料当真实机构材料，不标 B 级
- 不覆盖原件，先归档
- 不把搜索摘要当全文
- 网络失败写 `pending_sources.md` 后停止，不无限重试
- 不为凑数重复计数

## 搜索不可用时

- 固定 URL 清单 + `urllib` 直链抓取
- Wikipedia 用 REST API；论文用 PubMed E-utilities/PMC；元数据用 Crossref/OpenAlex
- 指南/招聘/科普优先人工下载 HTML/PDF 到 `inbox/`，再 `batch_ingest`
- 通用搜索只用于发现 URL，不作为证据

## 优先级

P0：资料真实性、去重、核验、运行记录。
P1：更新、文档、整理卡。

今天先完成阶段 0–2，确认唯一真实来源 ≥30、每方向 ≥6，再继续阶段 3–6。
