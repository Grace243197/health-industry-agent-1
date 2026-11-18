# config 说明

本目录只有一个运行时配置文件 `project.json`，所有字段都会被子智能体读取。下面按字段解释含义与计数范围。

## 顶层字段

| 字段 | 含义 | 备注 |
| --- | --- | --- |
| `domain` | 研究领域，例如 `成人睡眠健康` | 通用工具层面可替换 |
| `theme` | 主题，例如 `睡眠监测` | 决定知识库子目录与报告结构 |
| `region` | 主要地区 | 影响岗位、合规、科普材料范围 |
| `cutoff_date` | 资料截止日期 | 之后发布的不主动纳入 |
| `scenario` | 研究情境 | 用于报告引言与范围界定 |
| `topics` | 四个方向及其研究问题 | 见下方 |
| `paths` | 知识库、输出、runs、inbox 的相对路径 | 一般不改 |
| `web_enabled` | 是否允许联网 | 默认 `false`，需人工打开 |
| `limits` | 单次任务的各项上限 | 见下方 |
| `model` | 模型配置 | **不写密钥**，只写 provider/model/环境变量名 |
| `report` | 报告语言、是否含岗位分析、是否含跨方向综合 | |

## `topics` 结构

```json
"topics": {
  "<direction_code>": {
    "name": "方向中文名",
    "questions": ["问题1", "问题2", "问题3"]
  }
}
```

- 方向代码固定为 `RD` / `CL` / `AD` / `PC`
- 每个方向建议 2–3 个问题
- 问题应当可回答、可核验，避免空泛

## `limits` 计数范围

所有计数都是**单次 run 内**的累计值，重试也计入：

| 字段 | 计数范围 |
| --- | --- |
| `max_sources_per_run` | 一次 run 中新入库的来源数（去重后） |
| `max_web_searches` | `web_enabled=true` 时的搜索调用次数 |
| `max_web_fetches` | `web_enabled=true` 时的页面抓取次数 |
| `supplement_rounds` | 研究后发现缺口、回到收集阶段的轮次 |
| `max_retries` | 单个失败操作的重试次数 |
| `timeout_seconds` | 单个 agent 的超时 |
| `max_steps_per_agent` | 单个 agent 的最大步数（含工具调用） |
| `max_tool_calls` | 整个 run 的工具调用总次数 |

达到任一上限 → 保存已有结果，标 `status: partial`，进入收尾阶段。

## `model` 字段

- `provider`：模型提供商（openai / anthropic / dashscope / local 等）
- `model`：具体模型名
- `api_key_env`：**环境变量名**，例如 `DASHSCOPE_API_KEY`；不要把密钥写进配置文件
- `temperature`：建议 0.2–0.4（研究任务偏低）

## `report` 字段

- `language`：报告语言，例如 `zh-CN`
- `include_job_analysis`：是否包含 4 个代表岗位分析
- `include_cross_direction_synthesis`：是否包含跨方向综合分析
