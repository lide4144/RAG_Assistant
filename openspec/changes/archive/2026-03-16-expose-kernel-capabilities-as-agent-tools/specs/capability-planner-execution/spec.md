## ADDED Requirements

### 需求:系统必须在执行前解析 registry 级 tool 定义
系统必须在本地执行任一 planner action 之前先从已注册的 tool registry 解析对应 tool 定义，并据此校验 `tool_name`、输入参数、依赖产物、`streaming_mode` 与 `evidence_policy`；禁止直接把 planner 生成的 action 名称当作未经校验的内部函数调用。

#### 场景:本地执行前先做注册校验
- **当** planner decision 选择 `catalog_lookup -> cross_doc_summary`
- **那么** runtime 必须先解析这两个 action 对应的 registry 定义，再进入具体执行步骤

### 需求:系统必须记录 planner 与 tool execution 的独立观测字段
系统必须在统一状态对象和运行 trace 中同时保留顶层 planner 字段与底层 tool execution 字段。tool execution 字段至少必须包含 `call_id`、`tool_name`、`tool_status`、`failure_type`、`streaming_mode`、`evidence_policy` 与 `produced_artifacts`；禁止仅通过 planner decision 推断实际执行结果。

#### 场景:顶层决策与底层执行可区分
- **当** planner 选择 `cross_doc_summary`，但执行阶段因依赖缺失而停止
- **那么** trace 中必须既能看到 planner 原始决策，也能看到该 tool 的实际失败状态与停止原因

## MODIFIED Requirements

### 需求:系统必须显式区分 Planner、Tool 与确定性 Pipeline 三层职责
系统必须显式区分 `LLM Planner`、`tool 层` 和 `确定性 pipeline / kernel` 的职责边界；Planner 必须负责理解、选择、排序、澄清和停止，tool 层必须负责基于注册契约执行受约束能力调用并返回结构化结果，确定性 pipeline 必须负责检索、证据门控、引用绑定、任务状态和可审计落盘；禁止任一层无边界吞并其他两层职责，也禁止 planner 直接调用未经过 tool registry 解析的 kernel 私有函数。

#### 场景:planner 仅决定调用关系
- **当** planner 判定一次请求需要先查论文集合再做跨文档总结
- **那么** planner 必须只输出受支持的调用顺序和参数，而不是直接绕过 tool/pipeline 自行生成最终证据化回答

#### 场景:tool 层承接受约束执行
- **当** planner 已选择某个已注册 tool
- **那么** runtime 必须先通过 tool 层解析和执行该调用，再由底层 pipeline 负责具体检索、citation 与 gate 约束

### 需求:系统必须为 Planner runtime 暴露稳定的 tool 调用契约
系统必须为 Planner runtime 暴露稳定的 tool 调用契约，使后续具体能力可以作为 planner 可调用工具接入；该契约必须至少支持 registry 级 tool 元数据、结构化输入、结构化结果、失败原因、流式支持声明、evidence policy、可观测元数据和依赖前序产物；禁止让 planner 直接耦合某个 kernel 内部函数的私有调用细节。

#### 场景:新能力以 tool contract 接入
- **当** 后续变更把 `catalog_lookup` 或 `paper_assistant` 能力整理为 agent tool
- **那么** planner runtime 必须能够通过统一 tool contract 调用它，而不要求 Gateway 或前端理解该工具的内部实现

#### 场景:runtime 读取 tool 元数据决定执行约束
- **当** 某个已注册 tool 声明 `streaming_mode=final_only` 且 `evidence_policy=citation_forbidden`
- **那么** runtime 必须按该元数据约束执行与结果组装，而不是由 planner 或 gateway 临时猜测

### 需求:系统必须提供 planner 与执行器观测字段
系统必须在运行 trace 中输出 planner runtime、tool 调用与执行链路观测字段，至少包含 `planner_used`、`planner_source`、`decision_result`、`primary_capability`、`knowledge_route`、`research_mode`、`requires_clarification`、`selected_tools_or_skills`、`planner_confidence`、`action_plan`、`selected_path`、`execution_trace`、`short_circuit`、`truncated`、`planner_fallback` 与 `planner_fallback_reason`，并能够区分 planner 级与 tool/pipeline 级降级；对于实际执行过的 tool，观测字段还必须包含 `call_id`、`tool_status`、`failure_type`、`streaming_mode`、`evidence_policy` 与 `produced_artifacts`；当触发回退时必须记录回退原因与停止点。

#### 场景:agent-first 链路可审计
- **当** 系统经由 planner runtime 完成一次单步或多步请求
- **那么** run trace 必须包含 planner 决策、tool 选择、执行轨迹、回退状态与停止原因，且字段可序列化并可用于后续评测

#### 场景:顶层策略与执行结果可共同审计
- **当** 系统经由 planner runtime 完成一次本地执行、联网委托、研究辅助委托或兼容回退
- **那么** run trace 必须同时记录顶层决策结果、执行路径和回退原因

#### 场景:tool 级元数据可追踪
- **当** 某个本地 tool 被实际执行
- **那么** trace 中必须能够还原该 tool 的调用标识、执行状态、evidence 约束和产物输出

## REMOVED Requirements
