## 为什么

当前项目已经完成 `introduce-langgraph-planner-shell`，证明系统可以在不推翻 `frontend -> gateway -> python kernel` 主链路的前提下增加顶层编排壳层。但原始演进路线仍偏“保守的 Planner/Skill 分层”，主要目标是把若干理解问题拆成独立能力并逐步接入，而不是让大模型真正承担顶层任务理解与工具选择。

随着路线澄清，项目当前目标已转向更明确的 agent-first 形态：由 LLM Planner 负责顶层操作理解、能力选择与调用编排；底层确定性 Pipeline 退到工具层，继续负责导入、检索、建图、证据门控、引用绑定与任务状态等稳定执行。

项目需要一个新的架构变更来正式完成这次方向切换，避免继续沿用“保守 skill 化”定义推进后续变更，导致实现形态与产品目标不一致。

## 变更内容

- 将现有 LangGraph planner shell 从“受控壳层”升级定义为“LLM-first planner runtime”。
- 明确顶层 LLM Planner 的职责：理解用户真实意图、决定调用哪些 skill/tool、选择执行顺序、决定何时澄清或回退。
- 明确底层 Kernel 的职责：作为稳定工具层，对外暴露可调用能力，但不再承担顶层操作理解。
- 将原先偏保守的若干后续变更重新定义为 agent-first 版本，统一收敛到“LLM 在上、工具在下”的新路线。
- 规定安全边界：即使采用 agent-first，系统仍必须保留 evidence gate、citation 约束、任务状态与失败回退，不允许把自由规划扩展为无边界自治。

## 功能 (Capabilities)

### 新增功能
- `capability-planner-execution`: 从“顶层壳层执行能力”升级为“LLM-first planner runtime”能力，定义顶层规划、工具选择、失败回退与状态观测边界。

### 修改功能
- `node-gateway-orchestration`: 明确 Gateway 如何承接 agent-first planner runtime 的调用与事件转发，同时继续保持前端协议统一入口。
- `paper-assistant-mode`: 重新定义论文助理模式在 agent-first 架构中的职责边界，确保研究辅助能力由 Planner 统一调度。

## 影响

- 架构定位：系统正式从“先做保守 skill 化”转向“LLM 顶层规划 + 底层工具执行”的混合架构。
- 后续变更：原 8 个变更中除 `introduce-langgraph-planner-shell` 外，其余数个变更需要重命名或重写边界，以适配 agent-first 目标。
- 设计边界：需要重新定义哪些能力是 Planner 决策、哪些能力是工具层暴露、哪些仍属于硬约束的稳定流水线。
