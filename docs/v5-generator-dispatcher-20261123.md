# V5 变更说明：生成 Agent + 调度 Agent

- 日期：2026-11-23
- 版本：`v5-generator-dispatcher`
- 前置：V4（采集 + 校验）
- 内核版本：`20261123.5`

---

## 1. 这一轮补了什么

V4 只做到"采集 + 校验"这一对。本轮补上「生成 + 调度」：

```
用户 → 调度 → 采集 / 知识库 / 生成 / 校验
                    ↑______________________|
                      校验驳回则回退一次
```

现在五个 Agent 里 **4 个可运行**（知识库尚未实现），调度已能真实调用采集并写审计。

---

## 2. 生成 Agent（`generator-agent/`）

**5 个工具**（与任务书 05 一致）：`search_knowledge` / `load_source_cards` / `read_file` / `list_dir` / `save_report`。

- **双源强制**做在 `preflight()` 里，不在提示词里靠自觉：固化基线或来源卡任一为空 → 直接拒绝生成并说明缺哪一路。`run_cli.py --task` 在进 Agent 前先跑它。
- **证据索引**：`search_knowledge` 返回的每条命中都带 `source_id` + 从 `registry.jsonl` 读到的 `evidence_level`；来源卡解析出 `is_corporate_material`，供模型判断"只能写企业声称"。
- **只写 reports/**：`save_report` 走沙箱，`../escape.md` 会被拒绝。

**修掉的一个真 bug**：中文检索原来把整个查询当一个 token，模型传"生成成人睡眠监测技术现状报告"这种整句时永远检不到。改为中文二元组切分（"睡眠""监测""技术"分别命中），实测同一句能命中 2 条。

---

## 3. 调度 Agent（`dispatcher-agent/`）

**7 个工具**：`run_collector` / `run_knowledge` / `run_generator` / `run_verifier` / `list_agents` / `read_file` / `list_dir`。
（任务书写"6 个工具"，其中 `read_file`、`list_dir` 合称一项，实际注册 7 个函数，`--check` 会打印 7。）

- **subprocess 隔离**：`[sys.executable, 下游 run_cli.py, "--task", task]`，带 `timeout`、捕获 `TimeoutExpired`、非零返回码如实回传 stdout/stderr，**不伪造下游结果**。
- **审计**：每次分发追加一行到 `audit/audit_log.jsonl`（时间/目标/任务/是否成功/返回码/摘要）。
- **驳回回退一次**：公共内核新增通用扩展点 `agentrc.after_tools()`。`run_verifier` 的输出里出现 `verdict=rejected` 时，钩子往会话追加重写指令并让循环继续；第二次驳回不再回退，交给用户。
- **只读约束**：`read_file` 只放行 `research-collector-agent/sources`、`generator-agent/reports`、`verify-agent/verifications`、`knowledge-agent/knowledge_base`、`runs`、`output`；读 `.env` 会被拒。

### 修掉的两个真 bug

1. **子进程中文乱码**：Windows 下子进程按 GBK 写管道、父进程按 UTF-8 读，导致"驳回"识别不出来、verdict 永远判 passed。修法：调用下游时显式注入 `PYTHONIOENCODING=utf-8`。
2. **`$q` 与 `$task` 混用**：我一开始把"清洗掉动词的检索词"当成"传给下游的任务"，下游拿到"成人睡眠监测行业"后匹配不到"调研"这个动作，直接不干活。修法：占位符分开——`$q` 用于检索词，`$task` 透传原句。

---

## 4. 还有一个我自己造成的事故（已修）

用 PowerShell 的 `Set-Content -Encoding UTF8` 改 `tools/sync_core.py`，把 UTF-8 中文注释读成 ANSI，写入后注释与下一行 `GENERATED = [` 粘连，直接 `IndentationError`。

**教训**：这台机器上不要用 PowerShell 改含中文的 UTF-8 源文件；要么用编辑工具，要么整份重写。已整份重写并恢复。

---

## 5. 实测

| 检查 | 命令 | 结果 |
|---|---|---|
| 内核指纹 | `python tools/sync_core.py --check` | 4 个 Agent 全部 `20261123.5`，一致 |
| 采集自检 | `run_cli.py --check` | 5 工具，`[OK]` |
| 校验自检 | `run_cli.py --check` | 4 工具，`[OK]` |
| 生成自检 | `run_cli.py --check` | 5 工具；双源缺失时正确报"拒绝生成" |
| 调度自检 | `run_cli.py --check` | 7 工具；3 个下游存在、知识库缺失并给出 WARN |
| 单元测试 | 四个目录 `unittest discover` | 5 + 8 + 9 + 10 = **32 个全过** |
| 真实路由 | `dispatcher run_cli.py --task "调研成人睡眠监测行业"` | `run_collector` 成功，耗时 27.9 秒，审计落 1 行 |
| 下游返回内容 | 同上 | 命中 European PMC 相关文献（柔性传感器 OSAHS 监测） |

生成 Agent 的双源实测（用 W2 素材）：

```
双源就绪：基线 2 份，来源卡 2 份。
【固化基线命中 2 条】
- [SRC001 | C] 澜猫睡眠X8产品手册 ...
- [SRC007 | A] LANMAO Sleep Recorder PSG validation ...
```

---

## 6. 还没做（诚实清单）

| 缺口 | 影响 |
|---|---|
| **知识库 Agent 未实现** | 调度里 `run_knowledge` 会如实返回"入口不存在"；`generator` 的双源基线目前是手工放的 W2 卡 |
| 真实模型未接入 | 所有 Agent 只跑过离线假模型；真正的生成质量、verdict 判定未验证 |
| 完整四段链路未串过 | 采集→知识库→生成→校验 只能在知识库补上后跑通 |
| 回退只在单元测试验证 | 真实驳回链路需要模型或人工构造驳回输出 |
| `ask_report` 未接调度 | 网页问答仍走 V3.1 自己的检索链路 |

---

## 7. 回滚

```bash
git revert <本次提交哈希>   # 只影响 generator-agent、dispatcher-agent、shared-core 与文档
```

`generator-agent/reports`、`dispatcher-agent/audit` 等运行产物已在 `.gitignore`。