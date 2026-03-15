## 上下文

当前 agent-first 路线已经明确三层边界：Python kernel 中的 planner runtime 负责顶层规划、tool 选择和受控回退；Gateway 负责前端统一入口、协议转发和兼容回退；前端继续通过统一聊天入口消费事件。现有 Gateway 协议已经稳定承载 `message`、`sources`、`messageEnd`、`error` 以及任务型事件，但对 planner runtime 的高层执行状态仍缺少明确语义。

如果继续只保留回答型事件，前端无法在统一入口下识别“当前正在规划”“即将运行哪个能力”“某个能力已完成”“本轮已降级到兼容路径”等 agent-first 执行状态。另一方面，如果直接透传 Python runtime 的内部 trace、LangGraph 节点名或底层调用栈，又会把 Gateway 变成与 runtime 强耦合的语义镜像层，破坏当前路线中“Gateway 统一入口但不承担 planner 真相源”的边界。

本次变更因此聚焦在协议层补洞：为 Gateway 增加一层稳定、有限、对前端友好的高层 agent 执行事件，同时继续保持现有聊天事件兼容，并明确 Gateway 不升级成重状态 agent runtime。

约束：

- 必须复用现有 `frontend -> gateway -> python kernel` 主链路。
- 必须保留 `message`、`sources`、`messageEnd`、`error` 兼容语义。
- 不设计前端展示组件、文案或交互动效。
- 不在 Gateway 中实现 planner 决策、tool registry 或执行编排。
- 不透传 LangGraph 节点、私有函数名、详细 prompt/trace 或任意内部调试事件。

## 目标 / 非目标

**目标：**

- 为 Gateway 定义一组稳定的高层 agent 执行事件，覆盖规划、tool 选择、tool 执行、tool 结果和受控降级。
- 明确这些事件与现有聊天事件如何并存、排序和闭合，避免破坏既有前端入口。
- 明确 Gateway 对 agent 事件的职责仅为接收、归一化、转发和兼容降级，而非解释 planner 内部语义。
- 约束事件粒度，只暴露前端真正需要的高层执行状态，不泄露过细内部 trace。
- 固化 fallback/degraded 语义，使受控降级与真正错误可以被协议层区分。

**非目标：**

- 不定义前端如何展示 planning 或 tool-running 状态。
- 不在 Gateway 中引入长期会话内存、计划状态机或 agent 执行器。
- 不规定 planner runtime 的内部节点拓扑、trace schema 或具体 tool 列表。
- 不替换现有 `message/sources/messageEnd/error` 事件，也不要求旧聊天流一次性迁出。
- 不要求 `Web`、`Hybrid` 或非 agent 路径立即产生相同的 agent 事件集。

## 决策

### 决策 1：新增事件限定为“高层执行阶段事件”，而不是内部 trace 透传

Gateway 只对外暴露有限的高层 agent 事件类型：

- `planning`: 表示 planner runtime 正在形成或已形成本轮顶层执行方向；
- `toolSelection`: 表示 runtime 已确定下一步要调用的受支持能力；
- `toolRunning`: 表示某个已声明能力已开始执行；
- `toolResult`: 表示该能力返回了结构化结果摘要或失败摘要；
- `fallback`: 表示 runtime 触发了受控降级、兼容回退或停止继续扩张计划。

这些事件只允许包含稳定的高层字段，例如 `traceId`、`phase`、`tool_name`、`status`、`reason_code`、`fallback_scope`、`message` 摘要和是否仍将继续输出标准聊天事件。禁止包含 LangGraph 节点名、原始 trace span、prompt、底层函数路径、私有 registry 元数据或任意调试载荷。

原因：

- 前端需要的是“发生了哪类高层执行状态”，不是 runtime 内部如何一步步实现；
- 高层阶段事件能随 planner/runtime 实现演进保持稳定，而内部 trace 极易变化；
- 限制字段粒度能避免 Gateway 被迫跟随 Python runtime 内部重构。

替代方案：

- 直接透传 runtime trace：信息最全，但耦合过深，且明显超出前端稳定协议需要。
- 只保留 `message` 与 `error`：兼容性最好，但不足以支持 agent-first 执行状态感知。

### 决策 2：新增 agent 事件作为增强层，与既有聊天事件并存而非替代

现有 `message`、`sources`、`messageEnd`、`error` 继续作为统一聊天输出的基础事件。新增 agent 事件是可选增强层：

- agent 路径命中时，Gateway 可以在回答流开始前或过程中插入高层执行事件；
- 最终用户回答、来源和结束闭合仍必须通过现有标准事件完成；
- 对于未命中 agent-first 路径或后端未提供高层执行事件的情况，Gateway 仍必须只靠现有标准事件完成一次正常响应。

原因：

- 现有前端入口和兼容链路已经依赖基础聊天事件，不能被新协议打断；
- agent 事件的存在不应成为正常回答闭合的前提条件；
- 并存模型允许逐步迁移，降低对旧客户端和非 agent 路径的冲击。

替代方案：

- 用新的 agent 事件替换旧聊天事件：协议破坏性过强，且会扩大前端改造面。
- 所有路径都强制输出完整 agent 事件：对非 agent 路径没有必要，也会增加适配负担。

### 决策 3：Gateway 只做事件归一化与转发，不持有重状态执行上下文

Gateway 必须把 agent 事件视为“请求范围内的流式协议片段”，只负责：

- 关联 `traceId/requestId`；
- 校验事件类型是否属于受支持的有限集合；
- 进行轻量字段归一化与兼容补齐；
- 与现有 `message/sources/messageEnd/error` 共同输出给前端；
- 在 runtime 无法提供 agent 事件时退回到现有兼容行为。

Gateway 禁止承担：

- planner 状态机持久化；
- tool registry 查询与语义判断；
- 根据 agent 事件二次推导新的执行路径；
- 聚合跨请求的 agent 会话状态。

原因：

- agent-first 真相源已经固定在 Python kernel，Gateway 只能做协议层工作；
- 一旦 Node 侧持有更多执行状态，就会形成第二套 runtime 语义。

替代方案：

- 在 Gateway 聚合一套 agent session 状态：前端更省事，但会让 Gateway 变成半个 runtime。

### 决策 4：fallback 事件与 error 事件必须语义分离

`fallback` 代表“受控降级但请求仍在受支持路径内继续处理”或“本轮已明确停止 agent 扩张并切换兼容路径”；`error` 代表“本轮请求已失败或无法继续完成”。因此：

- 触发 planner fallback、tool fallback 或 legacy fallback 时，Gateway 必须优先输出 `fallback`，而不是直接把它等同为 `error`；
- 如果降级后仍成功产生最终回答，则后续仍可继续输出 `message`、`sources`、`messageEnd`；
- 只有请求无法继续、协议断裂或未受支持异常发生时，Gateway 才输出 `error` 作为失败终态。

原因：

- agent-first 路线明确要求“可控降级而非一失败就中断”；
- 若把 fallback 混同为 error，前端无法区分“已降级继续答复”与“请求彻底失败”。

替代方案：

- 统一都走 `error`：实现简单，但会损失 agent-first 回退语义。

### 决策 5：事件顺序只定义最小约束，不把 Gateway 绑定到固定内部步骤数

协议只规定最小顺序约束：

- `planning` 必须先于由该规划产生的 `toolSelection`、`toolRunning`、`toolResult` 或 `fallback`；
- `toolSelection` 必须先于对应的 `toolRunning`；
- `toolRunning` 必须先于对应的 `toolResult` 或由该步触发的 `fallback`；
- `messageEnd` 或 `error` 负责关闭本轮响应；
- 允许某些步骤缺省，例如单步 fallback 可以在 `planning` 后直接输出 `fallback`。

协议不要求 Gateway 知道 planner 总共有几步，也不要求所有工具都必须逐条发出事件，只要求已经发出的事件满足因果顺序且字段足够闭合。

原因：

- planner runtime 未来可能从规则规划演进到 LLM 规划，多步数和执行方式都会变化；
- 最小顺序约束足以支持前端消费和测试，而不会把 Gateway 锁死到某种内部实现。

替代方案：

- 规定完整固定状态机：看似清晰，但会过度绑定 runtime 内部实现。

## 风险 / 权衡

- [高层事件过少，前端信息不够] → 保留有限必需字段和摘要字段，后续若确有稳定需求再单独扩展事件语义。
- [高层事件过多，逐步滑向 trace 透传] → 明确禁止内部节点名、prompt、私有函数路径和详细 span 数据进入 Gateway 协议。
- [兼容旧链路导致协议双轨] → 以现有聊天事件为基座，要求新增 agent 事件只能增强不能替代，逐步推进消费端升级。
- [fallback 与 error 被实现层混淆] → 在规范中强制区分“受控降级”与“失败终止”，并要求对应事件分别建模。
- [Gateway 逐步积累执行状态逻辑] → 在规范中明确 Gateway 禁止做 planner 决策、tool 选择和跨请求状态管理。

## 迁移计划

1. 在 OpenSpec 中新增 `gateway-agent-execution-events` 能力，并更新 `node-gateway-orchestration` 的协议边界。
2. 在 Gateway 与 Python kernel 适配层约定最小 agent 事件 envelope，确保仅承载高层状态字段。
3. 让 Gateway 在不破坏现有 `message/sources/messageEnd/error` 的前提下支持插入 agent 高层事件。
4. 为 planner/runtime 回退路径补充 `fallback` 语义，确保兼容降级与请求失败可区分。
5. 通过契约测试验证事件类型、最小顺序、兼容缺省和 fallback 行为。

回滚策略：

- 若新增 agent 事件在实现阶段不稳定，Gateway 可以停止输出这些增强事件，继续仅输出现有基础聊天事件；
- 由于本变更不要求移除现有协议，因此回滚成本主要是停用新增事件映射，而非恢复旧入口。

## 开放问题

- `toolResult` 是否需要统一包含极简结果分类字段，例如 `result_kind=final|intermediate|empty|failed`，以减少前端猜测？
- `fallback` 是否需要进一步区分 `planner`、`tool`、`legacy` 三类 scope，还是只保留通用受控降级语义？
- 后续如果 `Web` 或 `Hybrid` 也进入 planner runtime，是否沿用同一高层事件集合，还是允许某些路径只输出子集？
