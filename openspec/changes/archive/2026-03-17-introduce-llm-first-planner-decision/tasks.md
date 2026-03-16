## 1. Planner Decision Contract

- [x] 1.1 为 LLM planner 定义与现有 runtime 兼容的最小 decision schema，并在 Python 端提供可复用的解析/序列化结构
- [x] 1.2 在 planner runtime 中接入可切换的 planner source 模式开关：`rule_only`、`shadow_compare`、`llm_primary_with_rule_fallback`
- [x] 1.3 将现有 rule planner 输出对齐到同一 decision schema，确保 shadow 对比与回退共用同一结构

## 2. Validation Gate

- [x] 2.1 在 runtime 中实现 LLM planner decision 的结构合法性校验，并为拒绝结果定义稳定 reason code
- [x] 2.2 在 runtime 中实现 decision 的语义一致性校验，包括 `decision_result`、`clarify_question`、`strictness` 与 `action_plan` 的组合约束
- [x] 2.3 在 runtime 中实现 action registry、依赖、步数和参数的执行合法性校验
- [x] 2.4 在 runtime 中实现基于 policy flags 的策略合法性校验，并在拒绝时优先回退到 rule planner

## 3. Shadow Compare And Observability

- [x] 3.1 为同一请求并行生成 rule planner 与 LLM planner decision，并记录 validation 结果与实际执行来源
- [x] 3.2 为 shadow mode 记录关键字段级 diff，包括 `primary_capability`、`strictness`、`decision_result`、`requires_clarification`、`selected_tools_or_skills` 与 `action_plan`
- [x] 3.3 为 shadow 样本预留人工评审标签位，并定义 `llm_better`、`rule_better`、`tie`、`both_bad` 的写入结构

## 4. Policy And QA Boundary Refactor

- [x] 4.1 识别并抽离 `qa.py` 中面向用户姿态的规则，使 kernel 改为输出证据不足、前置条件不足与 citation 不完整等约束信号
- [x] 4.2 将研究辅助与 summary 场景中的澄清、部分回答和拒答优先级提升为 planner / policy 决策
- [x] 4.3 将连续澄清上限后的低置信可追溯回答行为改造为 planner / policy 可追踪决策，而不是 `qa.py` 内部隐式例外

## 5. Gateway And Frontend Compatibility

- [x] 5.1 保持 Gateway 在 planner source 迁移期继续输出稳定的高层 `planning / tool / fallback` 事件与标准聊天闭环
- [x] 5.2 确保 LLM decision reject、rule fallback 与 legacy fallback 在 Gateway 事件中可区分但不暴露私有 validation 细节
- [x] 5.3 确保前端聊天页在 shadow mode 与 planner source 切换期间仍只呈现单一主回答流，并保持历史会话与输入交互稳定

## 6. Evaluation And Rollout

- [x] 6.1 组织多轮追问、summary vs strict_fact、paper assistant、control anchor 与 web delegation 等高风险 shadow 样本集
- [x] 6.2 为 shadow 样本建立人工评审流程与判定标准，用于比较 rule planner 与 LLM planner 的体验收益
- [x] 6.3 定义从 `rule_only` 到 `shadow_compare` 再到 `llm_primary_with_rule_fallback` 的灰度准入门槛与回滚条件
