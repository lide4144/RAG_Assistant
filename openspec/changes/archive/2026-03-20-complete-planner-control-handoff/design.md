## 上下文

当前仓库已经具备多项 `agent-first（智能体优先）` 迁移前提：

- `LangGraph shell（LangGraph 壳层）` 已存在，`Local` 模式可通过 `/planner/qa*` 入口进入 `planner runtime（规划运行时）`。
- `gateway routing（网关路由）` 已可优先把本地聊天请求发往 planner 入口，并保留 `legacy fallback（旧链路回退）`。
- `capability planner（能力规划器）` 已能输出 `planner decision（规划决策）`、`action plan（动作计划）` 与 `fallback（回退）` 字段。
- `agent events（智能体事件）`、`trace fields（追踪字段）` 与 `tool contract（工具契约）` 已形成基本外壳。

但用户可见行为仍未真正迁移，原因不是“planner 壳层缺失”，而是 `interaction authority（交互裁判权）` 仍然分散在多个层级：

- `planner / policy（规划器 / 策略层）` 在上游给出一轮规划结果；
- `legacy qa flow（旧问答主链）` 在中下游继续根据旧规则改写请求处理姿态；
- `sufficiency gate（充分性门控）` 与 `evidence gate（证据门）` 仍可能在底层直接决定 `clarify / refuse / partial answer（澄清 / 拒答 / 部分回答）`；
- `multi-turn clarification（多轮澄清）` 仍部分依赖分散的状态拼接与尾部规则。

这导致系统虽然具备 `planner shell（规划壳层）`，但尚未形成 `single interaction authority（单一交互裁判）`。本次变更的目标是完成真正的 `control handoff（控制权交接）`。

约束：

- 必须保留现有 `frontend -> gateway -> python kernel` 主链路。
- 必须保留 `citation contract（引用契约）`、`evidence validation（证据校验）`、`execution limits（执行上限）` 与 `trace logging（追踪日志）`。
- 不通过新增更多顶层规则分支来修补体验。
- 不要求本次变更同时重写 `Web / Hybrid` 所有执行路径。

## 目标 / 非目标

**目标：**

- 明确 `planner / policy（规划器 / 策略层）` 是唯一的 `final interaction authority（最终交互裁判）`。
- 将 `kernel / qa（内核 / 问答链）` 改造成只返回 `constraints envelope（约束信封）` 与执行结果，不再直接输出最终用户姿态。
- 将 `sufficiency gate（充分性门控）`、`evidence gate（证据门）` 等组件降级为 `guardrails（护栏）`，只负责约束，不再直接裁决。
- 让 `multi-turn clarification state（多轮澄清状态）` 收敛到统一的 `planner state（规划器状态）`。
- 为 trace（追踪）补充可以证明“谁做了最终决定”的稳定字段。

**非目标：**

- 不新增新的 `agent tools（智能体工具）`、研究辅助能力或前端 UI 能力。
- 不优化答案质量、检索质量或模型能力本身。
- 不重新设计 `gateway event protocol（网关事件协议）`。
- 不通过继续细化 `if-else heuristics（启发式规则）` 来解决顶层交互问题。
- 不在本次变更中统一所有 `Web / Hybrid` 路径的顶层控制。

## 决策

### 决策 1：将 `planner / policy（规划器 / 策略层）` 定义为唯一的最终交互裁判

从本次变更开始，任何用户可见的顶层交互姿态都必须由 `planner / policy（规划器 / 策略层）` 给出最终结果，包括：

- `execute（执行）`
- `clarify（澄清）`
- `partial_answer（部分回答）`
- `refuse（拒答）`
- `delegate（委托到受支持路径）`

底层组件不得再独立生成这些姿态作为最终用户可见结果。

原因：

- 当前系统的核心问题不是缺少 planner，而是存在多个交互裁判。
- 若 `qa.py`、`sufficiency gate（充分性门控）`、`evidence gate（证据门）` 仍能在 planner 之后改写结果，则 planner 只能是外壳，不是真正的 `source of truth（真相源）`。
- 只有先明确顶层裁判权归属，才能让后续行为回归、trace 与调试口径稳定。

替代方案：

- 继续允许 `planner（规划器）` 给建议、由 `qa.py` 尾部决定最终姿态：这会延续当前“planner-wrapped but not planner-led（被规划器包裹但不由规划器主导）”的问题。

### 决策 2：`kernel / qa（内核 / 问答链）` 只返回结果与约束信号，不再直接输出最终交互姿态

本次变更将 `legacy qa flow（旧问答主链）` 重定义为 `execution engine（执行引擎）`。它可以返回：

- `retrieval results（检索结果）`
- `candidate answer material（候选答案材料）`
- `metadata results（元数据结果）`
- `citation legality（引用合法性）`
- `evidence sufficiency（证据充分性）`
- `dependency failures（依赖失败）`
- `short circuit reasons（短路原因）`

但它不得直接把 `clarify / refuse / partial answer（澄清 / 拒答 / 部分回答）` 作为最终用户结果写死。

原因：

- 旧 QA 流最有价值的部分是检索、引用、证据和执行稳定性，而不是顶层交互判断。
- 让它只返回结构化约束，可以保留现有确定性能力，同时结束其越权裁决用户体验的问题。

替代方案：

- 保持 `qa.py` 直接输出最终姿态，仅在上层包装解释：这只会把多裁判问题藏起来，不会消失。

### 决策 3：将 `sufficiency gate（充分性门控）` 和 `evidence gate（证据门）` 降级为 `guardrails（护栏）`

`sufficiency gate（充分性门控）`、`evidence gate（证据门）`、`citation mapping checks（引用映射校验）` 等底层组件继续存在，但它们的职责改为：

- 检测回答是否合法、可追溯、可落盘；
- 报告 `constraint type（约束类型）`、`reason code（原因代码）`、`severity（严重度）` 与可恢复性；
- 在必要时阻止不安全答案成型。

它们不得再单独决定最终要不要向用户输出 `clarify / refuse（澄清 / 拒答）`。

原因：

- 这些组件适合做 `hard validation（硬校验）`，不适合做 `interaction control（交互控制）`。
- 当前系统里“明确问题仍被机械澄清”“控制意图被送入证据门”等问题，本质上就是 guardrails 越权成了对话控制器。

替代方案：

- 保留 gate 直接输出用户姿态，再让 planner 尝试解释：会让责任边界继续模糊。

### 决策 4：引入统一的 `constraints envelope（约束信封）`

底层执行链必须向 `planner / policy（规划器 / 策略层）` 返回统一的 `constraints envelope（约束信封）`。最小字段至少包括：

- `constraint_type（约束类型）`
- `reason_code（原因代码）`
- `severity（严重度）`
- `retryable（是否可重试）`
- `user_safe_summary（面向用户的安全摘要）`
- `blocking_scope（阻塞范围）`
- `evidence_snapshot（证据快照）`
- `citation_status（引用状态）`
- `suggested_next_actions（建议后续动作）`

由 `planner / policy（规划器 / 策略层）` 读取这些约束，并统一决定最终交互姿态。

原因：

- 如果底层只返回自由文本错误或散落布尔字段，上层无法稳定地重新组装交互决策。
- 统一 envelope（信封）是把 `execution truth（执行真相）` 和 `interaction truth（交互真相）` 分开的关键。

替代方案：

- 继续使用分散字段和临时标志：会导致每个调用方都重新猜测底层语义。

### 决策 5：多轮澄清必须由统一的 `planner state（规划器状态）` 承接

所有 `pending clarify（挂起澄清）`、`follow-up merge（追问合并）`、`same topic / new topic（同话题 / 新话题）` 判断，最终都必须收敛到统一的 `planner state（规划器状态）` 中。

底层执行链不再各自维护额外的“半隐式澄清状态”来决定如何拼接用户输入。

原因：

- 当前多轮澄清闭环失效，根本原因是状态真相源不唯一。
- 用户补充线索后能否回到原问题，必须是顶层控制问题，而不是零散拼接规则问题。

替代方案：

- 继续保留各处局部补丁式状态拼接：短期可修个别问题，长期会继续漂移。

### 决策 6：trace（追踪）必须证明最终交互裁判权已完成交接

系统必须在 trace 中新增并稳定输出至少以下字段：

- `final_interaction_authority（最终交互裁判）`
- `interaction_decision_source（交互决策来源）`
- `planner_decision_result（规划器决策结果）`
- `kernel_constraint_summary（内核约束摘要）`
- `guardrail_blocked（护栏是否阻断）`
- `final_user_visible_posture（最终用户可见姿态）`
- `posture_override_forbidden（是否发生被禁止的尾部改写）`

要求：

- 一次请求的最终用户姿态必须能从 trace 中明确追溯到唯一来源；
- 若底层 guardrail（护栏）阻断了答案成型，也必须能区分“护栏阻断”与“最终姿态决定”的责任边界；
- 若仍发生 legacy tail override（旧链路尾部改写），必须被视为违反本变更目标的错误状态。

原因：

- 没有 trace 级证明，迁移完成与否只能停留在口头判断；
- 当前系统之所以容易误以为“已经迁完”，正是因为行为层权力边界没有被稳定记录。

## 目标架构

```text
用户请求
   │
   ▼
Planner / Policy（规划器 / 策略层）
   │  决定：
   │  - execute（执行）
   │  - clarify（澄清）
   │  - partial_answer（部分回答）
   │  - refuse（拒答）
   │  - delegate（委托）
   ▼
Tool / Execution Layer（工具 / 执行层）
   │  返回：
   │  - results（结果）
   │  - artifacts（产物）
   │  - constraints envelope（约束信封）
   ▼
Guardrails（护栏）
   │  检查：
   │  - citation legality（引用合法性）
   │  - evidence sufficiency（证据充分性）
   │  - execution legality（执行合法性）
   ▼
Response Composition（响应组装）
```

关键原则：

- `planner / policy（规划器 / 策略层）` 负责用户交互决策；
- `tool / execution（工具 / 执行层）` 负责能力执行与结构化结果；
- `guardrails（护栏）` 负责安全与合法性，不负责顶层交互裁决。

## 风险 / 权衡

- [短期内行为变化会更明显]：因为旧 `qa tail override（问答尾部改写）` 被移除，部分路径会暴露此前被掩盖的约束冲突。
- [底层 envelope（信封）设计不足会导致上层仍然难决策]：因此必须优先定义统一的 `constraints envelope（约束信封）`。
- [多轮状态收口会触及多个历史补丁点]：但这正是当前迁移无法闭环的根因，不能继续回避。
- [trace 字段增加复杂度]：这是必要成本，否则“是否迁完”仍然无法验证。

## 迁移计划

1. 识别并列出所有当前能够改写最终用户交互姿态的代码路径。
2. 定义统一的 `final interaction decision contract（最终交互决策契约）`。
3. 定义统一的 `constraints envelope（约束信封）`，要求 `kernel / qa（内核 / 问答链）` 按该结构返回约束。
4. 将 `sufficiency gate（充分性门控）`、`evidence gate（证据门）`、`citation checks（引用校验）` 改造成 guardrail-only（仅护栏）组件。
5. 移除或封禁 `legacy qa tail override（旧问答尾部改写）`。
6. 将多轮澄清闭环收口到统一的 `planner state（规划器状态）`。
7. 增加 trace 字段与验收用例，以行为验证“最终交互裁判已唯一化”。

## 开放问题

- `partial_answer（部分回答）` 是否需要成为一等决策结果，还是先作为 `execute（执行）` 的一种受限输出形态？
- `guardrail blocked（护栏阻断）` 发生时，planner / policy（规划器 / 策略层）是否应优先尝试 `clarify（澄清）`，还是允许直接 `refuse（拒答）`？
- `Web / Hybrid` 路径何时需要纳入相同的 `interaction authority（交互裁判）` 模型，而不只是保持局部兼容？
