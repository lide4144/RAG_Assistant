## 为什么

`shift-to-agent-first-planner-runtime` 已经把 LangGraph shell 定义成顶层 runtime，但系统仍缺少一份专门约束“Planner 如何决定澄清、本地检索、联网、研究辅助与回退”的规范。若这层策略不先固定，后续 tool 暴露、研究辅助能力和联网能力会继续各自生长，顶层语义会重新分散。

## 变更内容

- 定义顶层 `LLM Planner` 的最小输入上下文、结构化输出和有限决策结果，明确其只负责理解请求、选择 tool/skill、决定是否澄清以及是否走本地或联网路径。
- 定义 planner 的路由语义，覆盖 `clarify`、`local retrieval/tool execution`、`web research delegation`、`research assistant delegation` 与 `legacy fallback`，并明确禁止无限步自治。
- 定义 planner 失败回退、停止条件和最小可观测字段，保证 runtime 能区分“规划失败”和“执行失败”。

## 功能 (Capabilities)

### 新增功能
- `llm-planner-tool-selection-policy`: 定义顶层 planner 的输入/输出契约、决策结果、路由策略、失败回退和最小观测字段。

### 修改功能
- `capability-planner-execution`: 将现有 planner runtime 从“可执行壳层”补充为“受策略约束的顶层决策入口”，要求执行层消费标准化 planner decision。
- `paper-assistant-mode`: 将研究辅助能力明确收束为 planner 可选择的受控路径，而不是独立旁路模式。

## 影响

- Python planner runtime 状态对象、planner decision schema、tool/skill registry 接口与 fallback 分类。
- `Local` 与现有 `Web/Hybrid` 链路之间的顶层分流语义，但不修改 gateway 事件协议。
- 运行 trace、评测样本与调试日志中需要稳定记录 planner 决策与回退字段。
