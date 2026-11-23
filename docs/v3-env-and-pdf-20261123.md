# V3 变更说明：PDF 入库打通 + 环境隔离 + 联网探针

- 日期：2026-11-23
- 版本：`v3-pdf-ingest`
- 前置：V2（`261117-v2-final`）
- 适用：接手本项目的人 / 给老师的进度说明 / 下一次继续开发

---

## 0. 一句话总结

**修好了一个一直没被发现的断点：抓下来的 PDF 从来没进过知识库。**
顺带把 Python 环境改成虚拟环境隔离，并加了一个验证千问联网能力的最小探针。

---

## 1. 为什么做（问题证据）

| 现象 | 证据 |
|---|---|
| 抓取的 PDF 从未入库 | `tools/fetch_sources.py` 会把 PDF 存到 `inbox/pdfs/<id>.pdf`，但全仓库只有 `tools/ingest.py:95` 定义了一个 `extract_pdf_text()`，**没有任何地方调用它** |
| 实际入库只看 Markdown | `ingest.py` 的 `main()` 只调用 `ingest_notes()`，它扫描 `inbox/notes/**/*.md`；`inbox/pdfs/` 无人处理 |
| 结果来源偏科 | `PORTABLE_SETUP.md` §7 已记录「无论文和真实招聘样本」，根因之一就是论文 PDF 进了 `inbox/pdfs/` 却停在磁盘上 |
| `requirements.txt` 声明了 `pypdf>=3.0` | 声明了但没用起来，本机也没装，属于"纸面依赖" |

另外两个工程问题：

- **全局环境污染风险**：之前所有脚本直接用系统 Python 3.12 全局环境跑，装依赖会污染整台机器。
- **千问联网能力未经验证**：下一步采集 Agent 要用 `enable_search` 做候选 URL 发现，但官方文档没说清 `search_info` 的确切层级，不能靠猜写代码。

---

## 2. 改了什么（逐文件）

### 2.1 `tools/ingest.py`（核心修复）

| 改动 | 说明 |
|---|---|
| 新增 `ingest_pdfs(run_id)` | 扫描 `inbox/pdfs/**/*.pdf`，pypdf 抽文字 → 分配 S### → 存 `raw.pdf` + `extracted.md` → 写卡片 → 追加 `registry.jsonl`，流程与 `ingest_notes()` 完全对称 |
| `main()` 接入 | `added.extend(pdf_added)`；失败的 PDF 进 `failed`，`01_collection.json` 的 `status` 自动变 `partial` |
| `extract_pdf_text()` 语义收紧 | 文档串改为「失败返回带方括号的标记串，由调用方识别，**不得当作正文入库**」；每页前保留 `<!-- page N -->` 便于引用定位 |
| 扫描件识别 | 两条阈值：正文 < 200 字符；或 ≥3 页时平均每页 < 80 字符 → 记入 `failed`，理由写明"疑似扫描件，需先 OCR" |
| 标题回填 | 论文文件名常是 `2023.05.30.23290376v1.full` 这类无信息串，此时用正文首行当标题；中文文件名（如「枕垫产品手册」）保持原样 |
| 卡片目录兜底 | `write_card()` 写入前 `mkdir(parents=True)`，否则全新克隆（`knowledge_base/` 被 gitignore）第一次跑会 `FileNotFoundError` |

**证据等级策略（重要，不是随手定的）**：PDF 一律沿用 `ingest_notes_v2.guess_meta_from_filename()` 的判定（默认 `C`，指南/标准 `B`），并统一追加
`PDF 自动入库，证据等级待人工核定`。
理由：自动入库的 PDF 分不清是同行评审论文还是产品宣传页，**只能给最低档 C 再由人升级**，这与架构说明里"C = 单一未交叉验证来源 / 企业宣传"的定义一致，不新增规则。

### 2.2 `tools/probe_search.py`（新增）

验证千问 `enable_search` 真实返回结构的探针：

- 同时测两条路：原生协议（`parameters.search_options`）与 OpenAI 兼容协议（请求体平铺）；
- 递归查找 `search_info` 节点，打印**实际路径**、字段名、前 3 条 `site_name / url`；
- 支持 `--show-raw`、`--save`；HTTP 非 200 也打印响应体；
- 只用标准库 `urllib`（与仓库其它 tools 一致，不引入 `requests`）；
- 无密钥时不发请求，打印 `.env` 位置并以退出码 2 结束。

**设计纪律**：探针只做"发现候选 URL"。`enable_search` 返回的是模型改写过的答案，**不是网页原文**，不能直接当证据；正文必须自己抓取后再定 A/B/C。

### 2.3 `PORTABLE_SETUP.md`

- §1 增补虚拟环境流程（`python -m venv .venv` → `.venv\Scripts\python.exe -m pip install -r requirements.txt`），避免污染全局 Python；
- §7 已知限制增补两条：扫描件 PDF 需 OCR；`kb_search.py` 仍是子串匹配。

### 2.4 仓库外同步（随交接包分发，不在本仓库）

教学原型 `agent_demo_submit/v1/code/` 同步增强（该目录在 `交接包-成人睡眠监测多Agent.zip` 内）：

- `agent/tools.py`：新增 `parse_document(source, max_chars)` 工具（HTML 用标准库 `html.parser`，PDF 用 pypdf，本地路径受沙箱限制，URL 只放行公网 http/https）+ `ToolRegistry.register_external()`（接入自带 JSON Schema 的外部工具）；
- `agent/prompts.py` / `core.py`：新增 `has_parser` 能力开关，维持"提示词提到的工具必须真实存在"这条不变量；
- `tests/test_offline.py`：新增 14 条用例，总数 79 → 93。

---

## 3. 怎么验证的（可复现）

环境：

```bash
python -m venv .venv
.venv\Scripts\python.exe -m pip install -i https://pypi.tuna.tsinghua.edu.cn/simple -r requirements.txt
```

安装结果：`pypdf 7.1.1`、`requests 2.34.2`（仅装在 `.venv`，全局环境未改动）。

### 3.1 PDF 入库（真实素材）

```bash
# 准备：把两份真实 PDF 放进 inbox/pdfs/
.venv\Scripts\python.exe tools/ingest.py --run-id smoke3
```

实测输出：

```
ingest: added 2 sources (2 from PDF, 0 PDF failed)
S001 | A wearable EEG device: LANMAO Sleep Recorder compared | other | C
S002 | 枕垫产品手册 | other | C
```

原文抽取量：论文 43,987 字符；产品手册 983 字符（4 页，密度约 245/页，判定为正常文本 PDF，未误杀）。

### 3.2 扫描件与去重

```bash
# 用 pypdf 生成 3 页空白 PDF 模拟扫描件，再跑一次
.venv\Scripts\python.exe tools/ingest.py --run-id smoke4
```

实测输出：

```
ingest: added 0 sources (0 from PDF, 1 PDF failed)
status: partial
failed[0].reason: PDF 共 3 页，只抽出 0 个字符（平均 0/页），疑似扫描件或图片排版，需先 OCR
```

同时验证了去重：已入库的 2 份 PDF 再跑一次不会重复登记。

### 3.3 单元测试（仓库外原型）

```bash
cd agent_demo_submit/v1/code
..\..\..\.venv\Scripts\python.exe -m unittest discover -s tests
# Ran 93 tests in 0.810s  OK

python -m unittest discover -s tests   # 全局环境（无 pypdf）
# Ran 93 tests in 1.712s  OK (skipped=1)   ← pypdf 相关用例自动跳过，不红
```

### 3.4 探针（未配密钥）

```bash
.venv\Scripts\python.exe tools/probe_search.py
# 未找到 DASHSCOPE_API_KEY。…… 退出码 2
```

---

## 4. 没做 / 待定

| 项 | 原因 | 建议 |
|---|---|---|
| `probe_search.py` 的真实请求验证 | 本机无 `DASHSCOPE_API_KEY`，拿不到真实返回结构 | 配好密钥后跑一次 `--show-raw --save`，再据此写采集 Agent 的搜索工具 |
| PDF 里 `type` 仍是 `other` | 自动判定"是否同行评审论文"不可靠，宁可留空让人工填 | 人工在 `cards/S###.md` 里补 `type: academic` 与 `evidence_level` |
| OCR | 本仓库只做文本层抽取，不装 OCR 引擎 | 若扫描件多，再引入 `pytesseract`/PaddleOCR，按需 |
| 5 个 Agent 可运行代码 | 属下一阶段（P1） | 按 `给千问的任务书/01~05` 补齐，`run_cli.py --check` 离线全绿为最小验收 |

---

## 5. 回滚方式

```bash
git revert <本次提交哈希>     # 只动 tools/ingest.py、新增 tools/probe_search.py 与文档
```

`.venv/` 与 `inbox/`、`knowledge_base/` 均在 `.gitignore` 内，不影响回滚。