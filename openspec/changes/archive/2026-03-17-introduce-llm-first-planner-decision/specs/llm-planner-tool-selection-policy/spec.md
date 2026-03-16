## 修改需求

### 需求:系统必须输出稳定的 planner decision 对象
系统必须让 planner 输出结构化 `planner decision` 对象，至少包含 `decision_version`、`planner_source`、`planner_used`、`planner_confidence`、`user_goal`、`standalone_query`、`is_new_topic`、`should_clear_pending_clarify`、`relation_to_previous`、`primary_capability`、`strictness`、`decision_result`、`knowledge_route`、`research_mode`、`requires_clarification`、`clarify_question`、`selected_tools_or_skills`、`action_plan` 与 `fallback`；禁止只返回自由文本解释、仅返回单个 intent 标签，或省略运行时依赖的最小上下文字段。

#### 场景:planner 输出完整决策对象
- **当** planner 完成一次顶层决策
- **那么** runtime 必须拿到可序列化的结构化决策对象，而不是依赖额外解析 planner 自由文本

#### 场景:planner 输出多轮关系字段
- **当** 用户请求涉及多轮追问、延续或换题判断
- **那么** planner decision 必须显式输出 `is_new_topic`、`should_clear_pending_clarify` 与 `relation_to_previous`，以便 runtime 不再依赖独立规则重新解释会话关系

### 需求:系统必须在规划失败时输出受控 fallback
当 planner 输出非法结构、缺失必要字段、引用未注册能力、命中策略禁止规则或置信度不足以继续执行时，系统必须输出 `decision_result=legacy_fallback` 或设置结构化 `fallback` 对象，并停止继续扩张计划；禁止在 planner 失败后无边界地再次自我重试。对于 LLM planner，runtime 必须先经过 validation gate，再决定是否接受该 fallback 语义。

#### 场景:planner 输出非法 tool 名称
- **当** planner 选择了 registry 中不存在的 tool
- **那么** runtime 必须将该结果视为 planner 失败并进入受控 fallback

#### 场景:LLM planner decision 被 validation 拒绝
- **当** LLM planner 输出在结构、语义、执行或策略任一层校验失败
- **那么** 系统必须进入受控 fallback，并记录稳定 rejection reason，而不是继续执行该 decision

## 新增需求

### 需求:系统必须允许 LLM planner 与 rule planner 并行产出可比较 decision
系统必须允许在同一请求上同时生成 LLM planner 与 rule planner 的结构化 decision，并保证两者使用同一最小 decision schema，以便进行字段级比较与灰度分析；禁止为 shadow 对比维护彼此不兼容的 planner 输出格式。

#### 场景:双 planner 输出可对齐比较
- **当** 系统运行在 shadow mode
- **那么** LLM planner 与 rule planner 的输出必须可以在 `decision_result`、`strictness`、`selected_tools_or_skills` 与 `action_plan` 等字段上直接对齐比较
