## 上下文

当前仓库已经完成 `shift-to-agent-first-planner-runtime`，顶层 LangGraph runtime、统一 state 与兼容回退已经存在；`capability-planner-execution` 也定义了 planner runtime、受限 action plan 和 fallback 大方向。但系统仍缺少一层更具体的“顶层策略真相源”：

- planner 到底读哪些输入字段；
- planner 必须输出哪些决策字段；
- “需要澄清 / 走本地 / 走联网 / 走研究辅助 / 直接回退”这些顶层结果如何被命名和消费；
- planner 选择 tool/skill 时是按什么注册信息决策，而不是直接耦合内部函数；
- 最小可观测字段要记录到什么程度，才能支持调试与后续评测。

这导致当前 agent-first 路线虽然有 runtime 壳层，但“顶层路由语义”仍不稳定，后续 `kernel tools`、`research assistant agent skills`、`agent observability` 等变更容易重复定义自己的 decision schema。

本次变更只处理顶层 planner 决策策略与路由语义，不处理：

- 前端 UI 如何展示 planning 状态；
- gateway 事件协议如何表达 planner/tool 事件；
- kernel 底层检索、citation、evidence gate 的重写；
- 无限步自治 agent 或开放式自主循环。

## 目标 / 非目标

**目标：**

- 定义顶层 planner 的最小输入 contract，覆盖用户请求、会话上下文、可用 tool/skill 清单与策略开关。
- 定义统一 planner decision schema，明确其输出字段、决策结果类型和有限 action plan。
- 定义 planner 如何决定 `clarify`、`local tools`、`web research delegation`、`research assistant delegation` 与 `legacy fallback`。
- 定义 planner 失败回退和最小可观测字段，保证后续实现与评测具有统一真相源。
- 保持 planner 为“单轮受限决策器”，而不是无限步自治 agent。

**非目标：**

- 不在本次变更中定义新的 gateway 事件帧或前端展示字段。
- 不在本次变更中定义具体每个 kernel tool 的内部参数细节。
- 不在本次变更中要求 `Web/Hybrid` 整体迁入 Python planner runtime 执行。
- 不在本次变更中引入开放式多轮自我反思、自动重规划或无上限重试。

## 决策

### 决策 1：定义独立的 planner policy schema，而不是把策略散落在 runtime state 的临时字段里

planner runtime 必须消费和产出一个稳定的 `planner decision` 对象。该对象与 runtime state 相关，但不等价于整个 state。它作为顶层策略 envelope，最少包含：

- `decision_version`
- `user_goal`
- `primary_capability`
- `decision_result`
- `requires_clarification`
- `knowledge_route`
- `research_mode`
- `action_plan`
- `selected_tools_or_skills`
- `planner_confidence`
- `fallback`

原因：

- runtime state 会持续扩张，不能让上层语义依赖大量实现细节字段；
- 独立 decision object 更适合被执行层、trace、评测和未来的 planner 替换实现共同消费；
- 这能把“策略决定了什么”和“运行时保存了什么”明确分开。

替代方案：

- 继续直接读写 runtime state 顶层散字段：短期快，但长期会让策略契约不可验证。

### 决策 2：planner 输入采用“请求 + 会话 + registry + policy flags”的四段式最小上下文

planner 输入只保留决策真正需要的上文，不把检索中间结果或 kernel 私有对象直接暴露给 planner。最小输入分为四段：

1. `request`
   - 当前用户输入、模式提示、显式限制词、用户是否请求联网等。
2. `conversation_context`
   - 最近一轮主题锚点、`pending_clarify`、上轮 planner 结果摘要。
3. `capability_registry`
   - 当前可调用 tool/skill 的名称、能力标签、输入前置条件、是否支持本地/联网/研究辅助。
4. `policy_flags`
   - 是否允许联网、是否允许研究辅助、步数上限、是否强制本地优先等。

原因：

- planner 需要的是“能做什么”和“当前允许做什么”，而不是底层所有实现细节；
- registry 驱动可避免把 tool 选择写成内部函数名白名单；
- policy flags 能把部署差异、实验开关和安全策略与请求理解分离。

替代方案：

- 直接把整个 runtime state 喂给 planner：信息冗余过大，且容易泄漏不该成为决策前提的内部细节。

### 决策 3：顶层决策结果固定为有限枚举，禁止开放式 agent loop

planner 的 `decision_result` 固定为有限集合：

- `clarify`
- `local_execute`
- `delegate_web`
- `delegate_research_assistant`
- `legacy_fallback`

其中：

- `clarify` 表示本轮先停，不执行 tool；
- `local_execute` 表示执行受限本地 tool/skill 计划；
- `delegate_web` 表示把请求交给既有联网/研究链路，不要求当前 runtime 模拟联网执行；
- `delegate_research_assistant` 表示进入研究辅助能力，但仍受 planner 与 kernel 边界约束；
- `legacy_fallback` 表示 planner 不继续 agent 路径，而交给兼容路径。

原因：

- 用户需求是“顶层策略与路由语义”，不是开放式 agent；
- 有限结果集合更容易测试、追踪和与现有链路对接；
- 明确 `delegate_web` 与 `delegate_research_assistant` 可以避免把所有路径都硬塞进本地 tool 执行器。

替代方案：

- 允许 planner 自由生成任意 route 名称：扩展快，但不可审计且容易破坏兼容回退。

### 决策 4：tool / skill 选择基于声明式 registry，而不是 planner 直连 kernel 函数

planner 只能从 `capability_registry` 暴露的条目中选择 `selected_tools_or_skills` 和 `action_plan`。每个条目至少提供：

- `name`
- `kind` (`tool` 或 `skill`)
- `capability_tags`
- `knowledge_scope` (`local`, `web`, `hybrid`)
- `supports_research_mode`
- `prerequisites`

planner 禁止引用未注册名称，也禁止依赖某个 Python 私有函数签名。

原因：

- 后续 `expose-kernel-capabilities-as-agent-tools` 需要一个统一入口；
- 研究辅助能力可能是 skill 或组合 tool，planner 不应区分它们的底层实现位置；
- registry 可使策略层与实现层解耦。

替代方案：

- 在 prompt 或代码里硬编码工具名与内部函数映射：会让后续变更难以维护。

### 决策 5：澄清、本地检索、联网和研究辅助必须互斥地产生顶层主结果

planner 必须输出一个主结果，而不是同时把多个互相冲突的路径并列为同级终态。例如：

- 需要澄清时，`decision_result=clarify`，不得同时执行 `local_execute`；
- 需要联网时，`decision_result=delegate_web`，不得伪装成本地 tool 计划；
- 进入研究辅助时，`decision_result=delegate_research_assistant`，但允许在其内部附带受限前置步骤，如先 `catalog_lookup` 再进入研究辅助。

原因：

- 顶层主结果是 runtime 选择下一条链路的依据；
- 如果同一轮同时输出多个主结果，执行语义会不稳定；
- 互斥主结果 + 有限 action plan 足以表达绝大多数请求。

替代方案：

- 允许并列多个终态标签：会让执行层需要再次“解释 planner”，违背单一真相源。

### 决策 6：失败回退分成“策略回退”和“执行回退”，最小观测字段只记录决策必需信息

planner policy 只要求记录最小可观测字段，不把完整评测体系放进本次变更。最小字段包括：

- `planner_used`
- `planner_source`
- `decision_result`
- `primary_capability`
- `knowledge_route`
- `research_mode`
- `requires_clarification`
- `selected_tools_or_skills`
- `action_plan`
- `planner_confidence`
- `planner_fallback`
- `planner_fallback_reason`
- `selected_path`

同时区分：

- `planner fallback`: 规划失败、决策非法、信心不足、策略禁止；
- `tool/pipeline fallback`: action plan 执行失败、依赖不满足、证据约束未通过。

原因：

- 用户明确要求“最小可观测字段”，而不是一次性定义全量 agent observability；
- 先记录决策真相源，后续 `add-agent-observability-and-evals` 再扩展更细指标。

替代方案：

- 现在就要求完整事件级观测：会把本次策略变更扩展成大而全的 observability 变更。

## 风险 / 权衡

- [planner decision schema 与现有 runtime state 有一定重叠] → 用独立 decision object 固定策略语义，允许 state 继续服务运行时实现细节。
- [`delegate_web` 只定义策略，不定义协议] → 明确本次只规定“何时委托”，后续 gateway/前端事件由专门变更处理。
- [registry 先于 tool 体系完全落地] → 本次只定义 registry 最小元数据，不强行定义所有工具参数。
- [研究辅助既像 skill 又像组合能力] → 在 policy 层统一用 `tool/skill registry` 表达，不要求现在决定其最终落位。
- [有限枚举可能看起来不够灵活] → 当前目标是稳定顶层路由；更细粒度的行动扩展留给后续 tool 变更。

## 迁移计划

1. 在本变更中新增 `llm-planner-tool-selection-policy` 规范，固定 planner 输入/输出和决策结果。
2. 更新 `capability-planner-execution`，要求 runtime 消费标准化 planner decision，而不是散乱字段。
3. 更新 `paper-assistant-mode`，把研究辅助入口显式绑定到 planner policy 的 `delegate_research_assistant` 结果。
4. 后续在实现变更中补齐：
   - planner decision schema 与 registry 数据结构；
   - local/web/research/legacy 路由分发；
   - trace 最小字段写入与回退分类。
5. 若后续实现验证不成熟，可继续保留现有规则 planner，只需让其输出同一 decision schema 即可，不需要推翻本次规范。

回滚策略：

- 若新 policy schema 在实现阶段证明不适配，可在规范层回退到 `capability-planner-execution` 的既有散字段模式；
- 由于本次不改 gateway 协议和 kernel 底层，回滚成本主要是 spec/design 文档级调整。

## 开放问题

- `delegate_web` 将来是否长期表示“委托既有 web/hybrid 链路”，还是最终演进为 planner runtime 内统一执行？
- `selected_tools_or_skills` 是否需要在下一变更中拆分为 `selected_tools` 与 `selected_skills` 两个稳定字段？
- planner 的 `planner_confidence` 是否应作为强制回退阈值，还是仅作观测字段，由策略配置决定是否触发 fallback？
