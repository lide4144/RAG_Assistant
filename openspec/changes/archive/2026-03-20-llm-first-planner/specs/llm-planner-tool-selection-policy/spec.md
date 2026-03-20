## 新增需求

### 需求:系统必须禁止未通过校验的规划结果伪装成回退决策
系统必须禁止将未通过 validation 的 `LLM planner decision` 改写为任意旧规则决策、隐式默认路径或未声明的内部回退动作；若无法继续执行，系统必须输出受支持的受控结束结果。

#### 场景:非法工具名不被改写成旧路径
- **当** planner 选择了 registry 中不存在的 tool
- **那么** runtime 必须将该结果视为无效 decision，并触发受控结束语义，而不得自动改写成旧规则路径

## 修改需求

### 需求:系统必须将顶层决策结果限制为有限枚举
系统必须将 `decision_result` 限制为 `clarify`、`local_execute`、`delegate_web`、`delegate_research_assistant` 或 `controlled_terminate` 之一；禁止 planner 生成未注册的顶层结果名称，也禁止继续使用 `legacy_fallback` 作为线上正式决策结果。

#### 场景:用户请求需要联网
- **当** 用户请求明确依赖外部最新网页信息，且当前策略允许联网
- **那么** planner 必须输出 `decision_result=delegate_web`，而不是伪装成本地检索计划

#### 场景:规划失败进入受控结束
- **当** planner 无法形成可执行且合法的顶层决策
- **那么** planner 必须输出 `decision_result=controlled_terminate` 或等价的受控结束语义，而不得输出 `legacy_fallback`

### 需求:系统必须在规划失败时输出受控结束语义
当 planner 输出非法结构、缺失必要字段、引用未注册能力、命中策略禁止规则或置信度不足以继续执行时，系统必须停止继续扩张计划，并进入 `controlled_terminate` 或等价的受控结束语义；禁止把失败重新解释为 `rule planner` 决策，也禁止通过隐式默认字段继续执行。

#### 场景:planner 输出非法 tool 名称
- **当** planner 选择了 registry 中不存在的 tool
- **那么** runtime 必须将该结果视为 planner 失败，并进入受控结束语义

#### 场景:LLM planner decision 被 validation 拒绝
- **当** LLM planner 输出在结构、语义、执行或策略任一层校验失败
- **那么** 系统必须进入受控结束语义，并记录稳定 rejection reason，而不是继续执行该 decision 或切换到 `rule planner`

### 需求:系统必须允许 LLM planner 与规则对比结果隔离记录
系统可以在同一请求上记录 `LLM planner decision` 的额外诊断结果用于评测或分析，但必须保证这些记录不属于线上正式决策对象，且不得影响 `decision_result`、`selected_tools_or_skills`、`action_plan` 或用户最终可见回答。

#### 场景:诊断对比不改变正式决策
- **当** 系统为了分析额外记录 planner 诊断信息
- **那么** 线上正式执行必须仍只使用 `LLM planner decision`，且诊断结果只写入诊断记录

## 移除需求
