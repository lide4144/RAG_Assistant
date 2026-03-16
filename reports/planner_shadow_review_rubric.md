# LLM Planner Shadow Review Rubric

## Labels

- `llm_better`: LLM decision 明显减少无谓澄清或更贴合用户目标，且未突破证据/策略边界。
- `rule_better`: rule decision 更稳妥或 LLM decision 引入错误姿态、错误能力选择、错误路由。
- `tie`: 两者体验与安全性基本等价。
- `both_bad`: 两者都未给出可接受的主路径决策。

## Review Checklist

1. 检查 `decision_result` 是否与用户真实意图匹配。
2. 检查 `strictness` 是否保持证据要求与回答姿态一致。
3. 检查 `selected_tools_or_skills` 与 `action_plan` 是否可执行。
4. 检查是否出现不必要澄清、错误拒答或不受控的 web delegation。
5. 检查最终主回答是否仍保持单一闭环，不因 shadow 样本影响用户输出。
