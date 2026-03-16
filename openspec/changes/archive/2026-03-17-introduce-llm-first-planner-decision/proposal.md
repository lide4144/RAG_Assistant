## 为什么

当前本地聊天链路虽然已经切入顶层 planner runtime，但顶层决策仍主要依赖规则 planner 和 `qa.py` 内部的交互策略规则。它们在多轮追问、总结与严格事实混合请求、助理型模糊需求、控制指令锚点复用等场景下过于僵硬，容易把语义误判直接暴露给用户，造成“系统不够智能”的体验。

现在推进这项变更，是因为仓库已经具备稳定的 planner runtime、tool registry 雏形、gateway planner-first 接入和 agent 事件槽位。继续把用户理解和交互姿态建立在规则主导上，会让后续 agent-first 路线持续被双重语义中心拖累。

## 变更内容

- 将顶层 planner 从 rule-dominant 过渡为 llm-first decision：由 LLM 产出与现有 runtime 兼容的结构化 planner decision，作为顶层语义理解与交互姿态的主入口。
- 新增 planner decision validation 契约：在 runtime 中校验 LLM planner 输出的结构、语义、一致性、registry 合法性与策略边界，不允许未校验的 LLM 决策直接驱动执行。
- 新增 shadow mode 与灰度迁移要求：支持 rule planner 与 LLM planner 并行决策、差异记录、人工评审与渐进式切流，先验证体验收益与安全边界，再切换主执行路径。
- 调整交互策略职责边界：逐步把“是否澄清、何时给部分回答、助理模式的交互姿态”从 `qa.py` 内部规则上移到 planner/policy 层；保留 evidence gate、citation、artifact 依赖、task state 和 trace 在 deterministic kernel/runtime。
- 明确前端与 gateway 在迁移期的兼容责任：保持现有聊天主协议可用，同时为 planning/tool/fallback 事件与 shadow 评估结果提供稳定观测边界。

## 功能 (Capabilities)

### 新增功能
- `llm-planner-decision-validation`: 定义 LLM planner 输出 schema、runtime 校验规则、拒绝原因、shadow 对比记录与灰度切换边界。

### 修改功能
- `capability-planner-execution`: 将顶层 planner runtime 从规则主导升级为支持 llm-first decision、validation gate、shadow mode 与渐进式主路径切换。
- `llm-planner-tool-selection-policy`: 将 planner 输出从规则选择语义扩展为 LLM 结构化决策语义，明确最小输出字段、一致性约束与能力选择边界。
- `paper-assistant-mode`: 将助理模式中的澄清、低置信部分回答和交互姿态从 `qa.py` 内部规则迁移到 planner/policy 层，同时保留证据与安全边界。
- `frontend-chat-focused-experience`: 调整前端对 planner/tool/fallback 状态的兼容要求，使其能承接 llm-first planner 与 shadow 迁移阶段的用户可见行为。
- `gateway-agent-execution-events`: 明确 gateway 在 llm-first planner 与 shadow 阶段的协议转发与事件保留责任，但不承接 planner 语义。

## 影响

- 受影响代码主要包括 `app/planner_runtime.py`、`app/capability_planner.py`、`app/qa.py`、`app/kernel_api.py`、`gateway/src/adapters/pythonKernelClient.ts`、`gateway/src/chatService.ts` 和前端聊天壳层事件处理。
- 受影响系统边界包括 Python planner runtime、tool registry/validation、QA 交互策略、gateway 事件转发、前端调试视图与运行 trace。
- 不计划在本变更中重写底层 retrieval、evidence gate、citation contract、task orchestration 或前端整体 UI，只调整顶层决策与交互策略职责分工。
