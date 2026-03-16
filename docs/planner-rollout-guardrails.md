# Planner Rollout Guardrails

## Promotion Gates

从 `rule_only` 晋级到 `shadow_compare` 前：

- LLM decision 结构校验 reject 率稳定下降并可归因。
- 高风险样本集已经覆盖多轮追问、summary/strict_fact、paper assistant、control anchor、web delegation。

从 `shadow_compare` 晋级到 `llm_primary_with_rule_fallback` 前：

- 人工评审标签中 `llm_better` 明显多于 `rule_better`。
- `reject -> rule fallback` 仍能稳定闭合聊天事件流。
- Gateway 与前端未出现重复 `messageEnd`、双主回答流或历史会话损坏。

## Rollback Conditions

- LLM validation reject 率突增。
- `strict_fact` 请求出现错误 tool 选择或 evidence gate 后的不受控姿态漂移。
- Gateway fallback 事件频繁退化为 legacy fallback。
- 前端聊天页出现消息不闭合、重复闭合或 session history 破坏。
