## ADDED Requirements

### 需求:系统必须让 planner runtime 消费标准化 planner decision
planner runtime 必须将顶层 `planner decision` 作为正式输入给后续路由与执行节点，并从中读取 `decision_result`、`knowledge_route`、`selected_tools_or_skills`、`action_plan` 与 `fallback`；禁止继续仅依赖散落在 state 中的临时决策字段解释下一步路径。

#### 场景:runtime 根据 decision_result 选择路径
- **当** planner 返回 `decision_result=delegate_web`
- **那么** runtime 必须将本轮请求委托到既有联网链路或受支持委托路径，而不是继续在本地执行 tool 计划

### 需求:系统必须区分顶层委托与本地执行
当 planner 输出 `local_execute`、`delegate_web`、`delegate_research_assistant`、`clarify` 或 `legacy_fallback` 时，runtime 必须按该顶层结果执行互斥路径；禁止把联网委托、研究辅助委托和本地 tool 执行混成同一类本地 passthrough。

#### 场景:研究辅助结果走独立委托语义
- **当** planner 返回 `decision_result=delegate_research_assistant`
- **那么** runtime 必须进入研究辅助能力路径，并保持该路径与普通本地 tool 执行在 trace 和 fallback 上可区分

## MODIFIED Requirements

### 需求:系统必须提供统一解析与能力规划节点
系统必须在进入主 QA 流之前调用统一的解析与能力规划节点，并一次性输出 `is_new_topic`、`standalone_query`、`primary_capability`、`decision_result`、`knowledge_route`、`research_mode`、`requires_clarification`、`selected_tools_or_skills`、`action_plan`、规划置信度与结构化 fallback；禁止将换题检测、路径选择与 tool 选择拆成多个彼此无约束的前置步骤。

#### 场景:统一节点输出顶层策略与执行计划
- **当** 用户输入“如果本地没有这方面的论文，就帮我联网查最近的综述，否则先总结库里的相关工作”
- **那么** 系统必须输出包含本地/联网路径判断、受限 action plan、fallback 语义与规划置信度的结构化结果

### 需求:系统必须支持受限的多动作计划执行
系统必须支持受限的顺序执行计划，允许的动作仅包括已注册且当前策略允许的 `tool/skill` 条目；对于本地执行路径，计划步数必须有硬上限，且每个后续步骤必须显式声明对前序产物的依赖。对于 `delegate_web`、`delegate_research_assistant`、`clarify` 与 `legacy_fallback`，系统禁止继续展开本地无限步计划。

#### 场景:本地执行路径保持有限步
- **当** 规划结果为 `decision_result=local_execute` 且 `action_plan` 包含 `catalog_lookup -> cross_doc_summary`
- **那么** 系统必须按声明依赖顺序执行有限步计划，并在达到步数上限或依赖失败时停止

#### 场景:联网委托不展开本地多步计划
- **当** 规划结果为 `decision_result=delegate_web`
- **那么** 系统必须停止本地 action plan 扩张，并将请求委托到既有联网路径

### 需求:系统必须提供 planner 与执行器观测字段
系统必须在运行 trace 中输出 planner runtime、tool 调用与执行链路观测字段，至少包含 `planner_used`、`planner_source`、`decision_result`、`primary_capability`、`knowledge_route`、`research_mode`、`requires_clarification`、`selected_tools_or_skills`、`planner_confidence`、`action_plan`、`selected_path`、`execution_trace`、`short_circuit`、`truncated`、`planner_fallback` 与 `planner_fallback_reason`，并能够区分 planner 级与 tool/pipeline 级降级；当触发回退时必须记录回退原因与停止点。

#### 场景:顶层策略与执行结果可共同审计
- **当** 系统经由 planner runtime 完成一次本地执行、联网委托、研究辅助委托或兼容回退
- **那么** run trace 必须同时记录顶层决策结果、执行路径和回退原因

## REMOVED Requirements
