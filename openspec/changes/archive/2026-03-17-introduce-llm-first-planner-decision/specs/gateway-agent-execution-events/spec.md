## 新增需求

### 需求:系统必须在 planner source 迁移期保留受控的高层事件语义
Gateway 在 `rule_only`、`shadow_compare` 与 `llm_primary_with_rule_fallback` 三种 planner source 模式下，必须继续只转发稳定的高层执行事件，并在发生 LLM decision reject、rule fallback 或 legacy fallback 时通过 `fallback` 事件表达受控降级；禁止将 shadow 对比细节、LLM 原始输出或私有 validation trace 直接透传给前端。

#### 场景:LLM decision 被拒绝时输出受控 fallback 事件
- **当** LLM planner decision 被 runtime validation 拒绝并回退到 rule planner 或 legacy 路径
- **那么** Gateway 必须输出高层 `fallback` 事件并继续保持标准聊天事件闭环，而不是透出内部 validation 细节

#### 场景:shadow 模式不透出双份规划细节
- **当** 系统运行在 shadow mode 且同时产出 rule planner 与 LLM planner 决策
- **那么** Gateway 必须仅向前端暴露稳定的主执行高层事件，而不是把两份 planner 细节同时作为用户事件流输出
