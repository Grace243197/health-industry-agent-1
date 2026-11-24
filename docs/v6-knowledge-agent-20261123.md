# V6 变更说明：知识库 Agent（两分法 + 人工冻结闸门）

- 日期：2026-11-23
- 版本：`v6-knowledge-agent`
- 前置：V5（生成 + 调度）
- 内核版本：`20261123.6`

---

## 1. 补上了最后一块

五个 Agent 现在是 **5/5 可运行**：

```
用户 → 调度 → 采集 / 知识库 / 生成 / 校验
                    ↑__________________|
```

之前 `run_knowledge` 只能如实返回"入口不存在"，现在调度能真正调起知识库并拿到结果。

---

## 2. 核心实现：资料两分法 + 人工闸门

`agent/knowledge.py` 是这一轮的重点，三个不变量都写在代码里，不靠提示词自觉：

| 不变量 | 实现 |
|---|---|
| 新素材只能进 staging | `preprocess()` 固定写 `staging/<sid>.md`，registry 记 `status="staging"`、`version=1` |
| 冻结必须有人批准 | `freeze()` 先校验 `approved_by`，空串或「待定/TODO/未知/无/n/a」一律 `PermissionError` |
| 只有 staging 能冻结 | 状态不是 `staging` 直接拒绝；二次冻结会被挡下 |
| frozen 只读 | `save_file` 只放行 `staging/` 前缀，写 `frozen/` 直接权限拒绝 |

`registry.jsonl` 每行一条：`source_id / title / source_type / url_or_path / evidence_level / status / approved_by / approved_at / frozen_at / version / path`。

**证据等级初判（保守）**：
- A：命中 pubmed / doi / europepmc / .gov / 国标 / 指南 / 论文 / 同行评审
- B：WHO / NHS / 白皮书 / 行业报告
- **C：命中"宣传/新闻/产品手册/官网/营销"——企业宣传优先判 C，永不因"是官网"抬高等级**
- 其余一律 C

---

## 3. 这一轮自己发现并修掉的四个 bug

写完后按"先跑测试再算完成"的规矩，逐个暴露：

1. **属性覆盖方法**：`self.archive = self.root/"archive"` 把同名方法 `archive()` 覆盖了，调用时报 `'WindowsPath' object is not callable`。改成 `self.archive_dir / staging_dir / frozen_dir`，并加了注释说明为什么不能叫 `self.archive`。
2. **表格体卡片解析失败**：W2 的来源卡是 `| **来源编号** | SRC001 |` 表格，而解析器只认 `- source_id: SRC001`，导致编号被重新生成、标题退化成文件名（出现过"Src007 被登记成 SRC001、标题叫 SRC007"）。改为双格式兼容，并补了专门的测试用例。
3. **学术论文判成 C**：判 A 的特征词里没有"论文/学术/同行评审"，而 W2 的 `来源类型` 写的是"论文（预印本）"。补进特征词后正确判 A。
4. **调度路由抢活**："列出所有来源"被调度自己的 `list_agents` 抢走（规则里有"列出"）。收窄为 `下游|有哪些 agent|调度状态`，并把"来源/素材/冻结/归档"划给 `run_knowledge`。

---

## 4. 实测

### 4.1 自检

```bash
cd knowledge-agent && python run_cli.py --check
# 工具数量 : 8（任务书"6 项"：5 个业务工具 + 沙箱 save_file/read_file/list_dir）
# staging / frozen / archive / registry 四项状态正常
# [OK]

cd dispatcher-agent && python run_cli.py --check
# 下游入口：采集 存在 / 知识库 存在 / 生成 存在 / 校验 存在
# [OK]（不再是 WARN）
```

### 4.2 真实流程（离线模型，工具真跑）

```bash
run_cli.py --task "预处理 research-collector-agent/sources/SRC007.md"
# 已入库：SRC007「A wearable EEG device...」证据等级：A（命中同行评审特征）状态：staging

run_cli.py --task "预处理 research-collector-agent/sources/SRC001.md"
# 已入库：SRC001「澜猫睡眠X8产品手册」证据等级：C（命中企业宣传特征）状态：staging

run_cli.py --task "把 SRC007 冻结进基线库，批准人：张三"
# 已冻结：SRC007 status：frozen approved_by：张三 版本：v2
```

`registry.jsonl` 实际内容（节选）：

```json
{"source_id": "SRC007", "evidence_level": "A", "status": "frozen",
 "approved_by": "张三", "approved_at": "2026-11-24T21:13:39",
 "frozen_at": "...", "version": 2, "path": "frozen/SRC007.md"}
{"source_id": "SRC001", "evidence_level": "C", "status": "staging",
 "approved_by": "", "version": 1, "path": "staging/SRC001.md"}
```

### 4.3 调度 → 知识库 两跳

```bash
cd dispatcher-agent && run_cli.py --task "列出所有来源"
# 工具序列: run_knowledge
# 共 2 条：SRC007 frozen | A | v2；SRC001 staging | C | v1
```

审计日志新增一行 `target="知识库 Agent"`。

### 4.4 测试

| Agent | 用例数 | 结果 |
|---|---|---|
| 采集 | 5 | OK |
| 校验 | 8 | OK |
| 生成 | 9 | OK |
| 调度 | 10 | OK |
| 知识库 | 20 | OK |
| **合计** | **52** | **全过** |

知识库 20 个用例覆盖：企业材料判 C、论文判 A、表格体卡片保号、原文逐字保留、越权路径拒绝、重复入库拒绝、**空/占位批准人拒绝（5 种写法）**、批准成功后状态与版本、二次冻结拒绝、归档移动、frozen 优先检索、save_file 不能碰 frozen。

---

## 5. 还没做

| 缺口 | 说明 |
|---|---|
| 真实模型未接入 | 所有判定仍是离线假模型走关键词；真实判级质量未验证 |
| 四段链路未一次性串通 | 现在只能一段一段调；调度一次只路由一个目标（离线规则），真实模型可多轮 |
| `ask_report` 未接调度 | 网页问答仍走 V3.1 自己的检索链路 |
| 人工闸门只在工具层 | 没有审批界面；`approved_by` 目前靠命令行传入 |

---

## 6. 回滚

```bash
git revert <本次提交哈希>
```

只影响 `knowledge-agent/`、`shared-core/model.py`（新增 `$sid/$approver` 占位符）、`dispatcher-agent/agent/agentrc.py`（路由规则）与文档。
`knowledge-agent/knowledge_base/`、`traces/` 已在 `.gitignore`。