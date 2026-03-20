# llm-planner-tool-selection-policy 规范

## 目的
定义顶层 planner 的输入/输出契约、有限决策结果、tool/skill 选择策略、失败回退和最小可观测字段，确保 agent-first 架构中的顶层路由语义稳定且可审计。

## 需求
### 需求:系统必须禁止未通过校验的规划结果伪装成回退决策
系统必须禁止将未通过 validation 的 `LLM planner decision` 改写为任意旧规则决策、隐式默认路径或未声明的内部回退动作；若无法继续执行，系统必须输出受支持的受控结束结果。

#### 场景:非法工具名不被改写成旧路径
- **当** planner 选择了 registry 中不存在的 tool
- **那么** runtime 必须将该结果视为无效 decision，并触发受控结束语义，而不得自动改写成旧规则路径

### 需求:系统必须为顶层 planner 提供最小输入 contract
系统必须为顶层 `LLM Planner` 提供稳定的最小输入 contract，至少包含 `request`、`conversation_context`、`capability_registry` 与 `policy_flags` 四段；禁止让 planner 直接依赖 kernel 私有对象、临时全局变量或未声明的检索中间产物作为必需输入。

#### 场景:planner 读取四段式输入
- **当** 一条新的聊天请求进入 planner runtime
- **那么** planner 必须能够从输入中读取当前用户请求、最近会话上下文、当前可用 tool/skill 注册信息与本轮策略开关

### 需求:系统必须输出稳定的 planner decision 对象
系统必须让 planner 输出结构化 `planner decision` 对象，至少包含 `decision_version`、`planner_source`、`planner_used`、`planner_confidence`、`user_goal`、`standalone_query`、`is_new_topic`、`should_clear_pending_clarify`、`relation_to_previous`、`primary_capability`、`strictness`、`decision_result`、`knowledge_route`、`research_mode`、`requires_clarification`、`clarify_question`、`selected_tools_or_skills`、`action_plan` 与 `fallback`；禁止只返回自由文本解释、仅返回单个 intent 标签，或省略运行时依赖的最小上下文字段。

#### 场景:planner 输出完整决策对象
- **当** planner 完成一次顶层决策
- **那么** runtime 必须拿到可序列化的结构化决策对象，而不是依赖额外解析 planner 自由文本

#### 场景:planner 输出多轮关系字段
- **当** 用户请求涉及多轮追问、延续或换题判断
- **那么** planner decision 必须显式输出 `is_new_topic`、`should_clear_pending_clarify` 与 `relation_to_previous`，以便 runtime 不再依赖独立规则重新解释会话关系

### 需求:系统必须将顶层决策结果限制为有限枚举
系统必须将 `decision_result` 限制为 `clarify`、`local_execute`、`delegate_web`、`delegate_research_assistant` 或 `controlled_terminate` 之一；禁止 planner 生成未注册的顶层结果名称，也禁止继续使用 `legacy_fallback` 作为线上正式决策结果。

#### 场景:用户请求需要联网
- **当** 用户请求明确依赖外部最新网页信息，且当前策略允许联网
- **那么** planner 必须输出 `decision_result=delegate_web`，而不是伪装成本地检索计划

#### 场景:规划失败进入受控结束
- **当** planner 无法形成可执行且合法的顶层决策
- **那么** planner 必须输出 `decision_result=controlled_terminate` 或等价的受控结束语义，而不得输出 `legacy_fallback`

#### 场景:用户请求信息不足
- **当** 用户请求缺少必要论文范围、主题或关键约束，无法安全进入执行
- **那么** planner 必须输出 `decision_result=clarify`

### 需求:系统必须让 planner 显式决定本地、联网和研究辅助路径
planner 必须在每轮决策中显式判断该请求是走本地能力、联网委托、研究辅助委托还是澄清/回退，并通过 `knowledge_route` 与 `research_mode` 表达结果；禁止把“是否联网”或“是否进入研究辅助”留给后续执行器隐式猜测。

#### 场景:本地论文问答优先本地路径
- **当** 用户问题可由本地论文库和已注册本地能力完成
- **那么** planner 必须输出本地 `knowledge_route` 并选择 `local_execute`

#### 场景:研究辅助请求进入研究辅助路径
- **当** 用户请求是论文比较、研究思路梳理或下一步建议，且研究辅助能力已注册并允许使用
- **那么** planner 必须输出 `decision_result=delegate_research_assistant`，并标记研究辅助模式

### 需求:系统必须基于声明式 registry 选择 tool 或 skill
planner 必须仅从 `capability_registry` 中声明存在且当前允许使用的条目里选择 `selected_tools_or_skills` 与 `action_plan`；每个被选择条目必须能够映射到注册名称、能力标签和前置条件。系统禁止 planner 直接依赖 kernel 内部函数名、硬编码未注册调用或推断不存在的能力。

#### 场景:未注册能力不可被选择
- **当** 某个 tool 或 skill 未出现在当前 registry 中
- **那么** planner 必须不选择该能力，并在必要时输出 `controlled_terminate` 或受控澄清

### 需求:系统必须限制 planner action plan 的步数与停止条件
当 `decision_result=local_execute` 或 `delegate_research_assistant` 时，planner 输出的 `action_plan` 必须是受限、有限步的顺序计划，并且必须显式满足步数上限、依赖关系与停止条件；禁止 planner 发起无限步循环、未声明依赖的隐式重规划或无上限自主重试。

#### 场景:本地复合查询形成有限计划
- **当** 用户输入“先找出昨天导入的 Transformer 论文，再总结它们的方法差异”
- **那么** planner 必须输出有限步 `action_plan`，且每步依赖关系明确

### 需求:系统必须在规划失败时输出受控结束语义
当 planner 输出非法结构、缺失必要字段、引用未注册能力、命中策略禁止规则或置信度不足以继续执行时，系统必须停止继续扩张计划，并进入 `controlled_terminate` 或等价的受控结束语义；禁止把失败重新解释为 `rule planner` 决策，也禁止通过隐式默认字段继续执行。

#### 场景:planner 输出非法 tool 名称
- **当** planner 选择了 registry 中不存在的 tool
- **那么** runtime 必须将该结果视为 planner 失败并进入受控结束

#### 场景:LLM planner decision 被 validation 拒绝
- **当** LLM planner 输出在结构、语义、执行或策略任一层校验失败
- **那么** 系统必须进入受控结束语义，并记录稳定 rejection reason，而不是继续执行该 decision 或切换到 `rule planner`

### 需求:系统必须记录最小 planner 可观测字段
系统必须为每轮 planner 决策记录最小可观测字段，至少包含 `planner_used`、`planner_source`、`decision_result`、`primary_capability`、`knowledge_route`、`research_mode`、`requires_clarification`、`selected_tools_or_skills`、`action_plan`、`planner_confidence`、`planner_fallback`、`planner_fallback_reason` 与 `selected_path`；禁止在没有这些字段的情况下将 planner 视为可审计。

#### 场景:planner 决策可追踪
- **当** 一次请求经过顶层 planner 决策后完成或回退
- **那么** trace 中必须能还原 planner 选了什么路径、为什么回退以及最终落到哪条执行路径

### 需求:系统必须允许 LLM planner 与规则对比结果隔离记录
系统可以在同一请求上记录 `LLM planner decision` 的额外诊断结果用于评测或分析，但必须保证这些记录不属于线上正式决策对象，且不得影响 `decision_result`、`selected_tools_or_skills`、`action_plan` 或用户最终可见回答。

#### 场景:诊断对比不改变正式决策
- **当** 系统为了分析额外记录 planner 诊断信息
- **那么** 线上正式执行必须仍只使用 `LLM planner decision`，且诊断结果只写入诊断记录
