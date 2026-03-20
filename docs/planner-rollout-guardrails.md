# Planner Rollout Guardrails

## Promotion Gates

从内部诊断阶段晋级到 `shadow_compare` 前：

- LLM decision 结构校验 reject 率稳定下降并可归因。
- 高风险样本集已经覆盖多轮追问、summary/strict_fact、paper assistant、control anchor、web delegation。

从 `shadow_compare` 晋级到正式 `llm_primary` 前：

- 人工评审结论中 `accepted` 明显多于 `incorrect`，且 `blocked` 样本持续下降。
- `reject -> controlled_terminate` 能稳定闭合聊天事件流且不产生双主回答。
- Gateway 与前端未出现重复 `messageEnd`、双主回答流或历史会话损坏。

## Rollback Conditions

- LLM validation reject 率突增。
- `strict_fact` 请求出现错误 tool 选择或 evidence gate 后的不受控姿态漂移。
- Gateway fallback 事件频繁退化为 `controlled_terminate` 且缺少稳定 reason code。
- 前端聊天页出现消息不闭合、重复闭合或 session history 破坏。
