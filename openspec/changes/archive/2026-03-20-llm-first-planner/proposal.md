## 为什么

当前仓库虽然已经引入 planner runtime，但顶层对话理解、追问/换题判断、工具选择与最终执行路径仍明显受 rule-heavy planner 主导，而现有规则控制已经无法满足最低可用要求。为了把系统推进到你期望的 “LLM as orchestration brain + bounded tools + hard guardrails” 形态，需要把顶层 planner 演进为真正的 LLM-first conversation interpreter，并明确由 LLM planner 成为正式主决策来源，而不是继续依赖旧规则链兜底。

## 变更内容

- 将顶层 planner 的主决策来源从以规则为主，调整为由 LLM decision 作为唯一正式主决策来源。
- 让 LLM 在统一 decision schema 下主导多轮关系判断，包括是否为新话题、是否清除挂起澄清、与上一轮的关系判定。
- 让 LLM 主导高层能力选择与顶层路径判断，包括是否查目录、是否走本地检索、是否做总结、是否进入研究辅助或触发任务型能力。
- 强化 runtime 对 LLM decision 的 validation、拒绝原因与运行时护栏，确保 LLM-first 迁移可审计、可约束，但不再回退到旧规则 planner 作为正式执行来源。
- 收紧 planner、tool 与确定性 pipeline 的职责边界，避免 planner 直接绕过 registry、kernel 安全边界或尾部护栏。

## 功能 (Capabilities)

### 新增功能
<!-- 无 -->

### 修改功能
- `capability-planner-execution`: 将 planner runtime 从“统一规划壳层”进一步收敛为 LLM-first 顶层编排入口，明确 LLM 作为唯一正式主决策来源的运行时语义。
- `llm-planner-tool-selection-policy`: 调整 planner decision contract，使 LLM 成为多轮关系判断、能力选择、顶层路径决策与有限步 action plan 的默认且唯一正式来源。
- `llm-planner-decision-validation`: 强化 LLM decision 的运行时校验、拒绝原因与失败语义，支撑 LLM-first 执行，但不再以 rule planner 作为常规回退路径。
- `control-intent-routing`: 将控制意图、追问/换题与结构化参数识别进一步并入 LLM-first conversation interpretation，而不是继续依赖独立规则链解释。
- `planner-interaction-authority`: 细化 planner 作为最终用户交互姿态唯一裁判时，在 LLM-first 模式下与底层约束信号、尾部规则和失败收束语义的责任边界。

## 影响

- 受影响代码主要包括 planner runtime、planner policy、decision schema、validation gate、tool registry 接口、聊天入口编排与 trace/observability 字段。
- 受影响系统行为包括顶层路径选择、澄清/执行/委托决策、工具选择顺序、旧规则 planner 的退出方式，以及 LLM planner 与既有 QA/Kernel 的交互边界。
- 该变更不直接要求移除 deterministic backend、evidence gate 或 citation guardrails；相反，需要它们继续作为 LLM-first planner 的硬约束与输出边界。
