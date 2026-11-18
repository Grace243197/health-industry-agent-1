# 便携版说明（V2 Final）

- 版本：`261117-v2-final`
- 打包日期：2026-11-17
- 用途：把当前项目复制到另一台电脑后，仍能查看报告、检索知识库、复跑核验与自检。

## 1. 环境要求

- Python 3.10 及以上
- 依赖：`pypdf`（只有解析 PDF 时需要；当前知识库以 HTML/文本为主）
- 安装：

```bash
pip install -r requirements.txt
```

- 不需要联网即可运行 `self_check.py`、`kb_search.py`、`evidence_verifier_v2.py`、`kb_updater.py`。
- 不需要 API Key 即可做本地检索、核验和自检；`config/project.json` 里的 `api_key_env` 只是模型配置说明，不写密钥。

## 2. 解压后先验证

进入解压后的项目根目录（有 `README.md` 和 `tools/` 的那一层）：

```bash
python tools/self_check.py --run-id 261117-v2-final
```

预期 8 项全部 PASS。

再试一次本地检索：

```bash
python tools/kb_search.py "CPAP" --limit 3
```

应返回来源编号、文件位置和原文片段。

打开最终报告：

```text
output/261117-v2-final_report.md
```

## 3. 目录说明

| 路径 | 内容 |
|---|---|
| `config/project.json` | 领域、主题、四方向问题、路径、运行上限、模型配置 |
| `knowledge_base/registry.jsonl` | 来源登记（32 份唯一真实来源） |
| `knowledge_base/sources/` | 原件 `raw.html` + 抽取文本 `extracted.md` |
| `knowledge_base/cards/` | 每份来源的整理卡 |
| `knowledge_base/topics/` | 9 个主题页 + 4 个岗位页 + 跨方向综合 |
| `tools/` | 采集、检索、核验、更新、自检脚本 |
| `runs/261117-v2-final/` | 本次运行的交接记录、核验结果、报告、修复日志 |
| `output/261117-v2-final_report.md` | 最终报告 |
| `docs/` | 差距报告、决策记录、变更说明、给 Qwen 的 prompt |
| `.qwen/agents/` | Qwen Code 的角色定义（可选） |

所有脚本都用相对路径，整个文件夹可以整体移动，不依赖 `D:\...` 这类绝对路径。

`docs/` 和 `PROMPT_QWEN.md` 里出现的 `D:\...` 是原机器上的记录/提示词，换机后按新路径调整即可，不影响脚本运行。

## 4. 跑一次新任务

1. 编辑 `config/project.json`：改 `domain`、`theme`、`region`、`cutoff_date` 和 `topics.*.questions`。
2. 按 `RUNBOOK.md` 的阶段执行：收集 → 研究 → 核验 → 更新 → 报告。
3. 联网抓取用：

```bash
python tools/fetch_sources.py --dry-run
python tools/fetch_sources.py --fetch --run-id <run_id>
```

4. 抓取失败会写 `knowledge_base/pending_sources.md`；不要用模拟材料补位。
5. 每次运行结束跑：

```bash
python tools/self_check.py --run-id <run_id>
```

## 5. 压缩包里刻意排除的内容

为了减小体积并避免历史模拟材料混入，以下内容没有打进压缩包：

- `.git/`（版本库与机器权限信息）
- `runs/` 下的旧运行和 `*.bak-*` 备份（只保留 `261117-v2-final/`）
- `output/archive/`、`output/261026-v1_report.md`（历史报告）
- `knowledge_base/topics/archive/`（主题页旧版本）
- `.qwen/settings.json`（本机权限设置；`.qwen/agents/` 保留）
- `__pycache__/`、`*.pyc`、系统缩略图等
- `inbox/notes/` 下 6 份模拟材料原文（2 份招聘、1 份指南、1 份标准、2 份科普）未打包；对应的排除标记见 `knowledge_base/registry.jsonl` 的 S027–S032

因此 `runs/261117-v2-final/05_kb_update.md` 和 `repair_log.md` 里提到的归档路径，在压缩包中不存在；它们只是原机器上的历史记录。

## 6. 模拟材料说明

`knowledge_base/simulated_sources/` 里是 S027–S032，已在 `registry.jsonl` 标记 `excluded: true`，不计入 32 份真实来源，也不作为证据引用。保留该目录仅用于审计“模拟材料如何处理”，不要把它当真实资料。

## 7. 已知限制

- 191 条核验判断中，102 条来自 4 个岗位页且没有 `source_id`，判为 `unverifiable`；原因是未找到中国大陆真实招聘样本。
- 来源以 Wikipedia 为主（27 份），另有 2 份会议纪要、2 份指南（NHS、WHO）、1 份机构资料（ResMed）；无论文和真实招聘。
- S033–S042 已入库并部分进入报告，但尚未深度整合进各方向主题页。
- `kb_search.py` 目前是精确关键词子串匹配，多词查询需要拆开搜。

## 8. 校验

- 最终报告与运行目录报告应完全一致：

```bash
sha256sum runs/261117-v2-final/04_report.md output/261117-v2-final_report.md
```

- 具体哈希、文件数、打包时的关键校验值见压缩包内 `PACKAGE_INFO.json`。
