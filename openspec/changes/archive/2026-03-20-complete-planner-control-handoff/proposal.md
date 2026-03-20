## 为什么

当前系统虽然已经具备 `planner runtime（规划运行时）`、`/planner/qa*` 入口、`gateway routing（网关路由）`、`agent events（智能体事件）` 与 `tool contract（工具契约）` 等迁移前提，但用户可见行为仍未完成真正迁移。

当前仍存在以下问题：

- `control intent（控制意图）` 仍会误入旧 `qa flow（问答主链）`，例如“用中文回答我”被送入 `evidence gate（证据门）`。
- 明确单篇论文问题仍会被旧 `clarify heuristics（澄清启发式规则）` 过度拦截，例如明确标题后仍要求补“主体限定”。
- `multi-turn clarification（多轮澄清）` 仍未形成稳定闭环，用户补充线索后常被重新路由到目录列举或再次澄清。
- `sufficiency gate（充分性门控）` 与 `evidence policy gate（证据策略门）` 仍在底层直接主导 `clarify / refuse / partial answer（澄清 / 拒答 / 部分回答）`，而不是仅输出 `constraints signals（约束信号）`。
- `legacy qa flow（旧问答主链）` 仍可在 planner（规划器）之后改写最终用户交互姿态，导致系统存在多个 `interaction authorities（交互裁判）`。

这说明当前系统已经 `planner-wrapped（被规划器包裹）`，但尚未 `planner-led（由规划器主导）`。

项目需要一个新的架构变更，完成真正的 `planner control handoff（规划器控制权交接）`：让 `planner / policy（规划器 / 策略层）` 成为用户交互姿态的唯一真相源，而让底层 `kernel / qa / gates（内核 / 问答链 / 门控）` 退回为 `guardrails（护栏）` 与 `execution engines（执行引擎）`。

## 变更内容

- 将 `planner / policy（规划器 / 策略层）` 定义为 `final interaction authority（最终交互裁判）`，唯一决定本轮请求是 `clarify / partial answer / refuse / execute（澄清 / 部分回答 / 拒答 / 执行）`。
- 将 `legacy qa flow（旧问答主链）` 改造为仅返回 `retrieval results（检索结果）`、`evidence constraints（证据约束）`、`citation legality（引用合法性）`、`dependency failures（依赖失败）` 等结构化信号，不再在尾部改写最终交互姿态。
- 将 `sufficiency gate（充分性门控）` 与 `evidence gate（证据门）` 收敛为 `guardrails（护栏）`，仅负责阻止不安全答案成型或报告约束，不再直接决定用户可见的澄清与拒答。
- 定义统一的 `interaction decision contract（交互决策契约）` 与 `constraints envelope（约束信封）`，明确顶层决策层与底层执行层之间的边界。
- 明确 `multi-turn clarification state（多轮澄清状态）` 必须由 planner state（规划器状态）统一承接，不再依赖分散的规则拼接。
- 为运行 trace（运行追踪）补充 `interaction authority（交互裁判）`、`decision source（决策来源）`、`constraint source（约束来源）` 等字段，确保每次 `clarify / refuse / partial answer（澄清 / 拒答 / 部分回答）` 都可审计其来源。

## 功能 (Capabilities)

### 新增功能

- `planner-interaction-authority`：定义最终交互姿态的唯一决策层与结构化决策契约。
- `kernel-constraint-envelope`：定义底层执行链返回给 `planner / policy（规划器 / 策略层）` 的统一约束信号结构。

### 修改功能

- `capability-planner-execution`：要求 `planner runtime（规划运行时）` 不仅是顶层入口，还必须成为最终用户交互姿态的唯一真相源。
- `sufficiency-gate`：要求其从最终裁判降级为 `guardrail-only（仅护栏）` 组件。
- `multi-turn-session-state`：要求澄清闭环由 `planner state（规划器状态）` 统一承接，而不是由旧 QA 规则拼接驱动。
- `control-intent-routing`：要求控制意图由 `planner / policy（规划器 / 策略层）` 直接识别并处理，不得再误入证据型 QA 主链。

## 非目标

- 不新增新的 `agent tools（智能体工具）` 或研究辅助能力。
- 不新增新的前端页面、视觉改版或 `gateway protocol（网关协议）`。
- 不优化答案内容质量本身，重点是交互控制权与行为一致性。
- 不在本次变更中统一 `Web / Hybrid` 的全部执行架构。
- 不通过继续追加顶层规则分支来修复用户体验问题。

## 影响

- 架构边界：系统将从“`planner shell（规划壳层）` + `legacy qa tail override（旧问答尾部改写）`”转为“`planner-led interaction（规划器主导交互）` + `kernel guardrails（内核护栏）`”。
- 代码边界：`qa.py`、`sufficiency.py`、`planner runtime（规划运行时）`、多轮澄清状态与 trace 写入逻辑都将受影响。
- 验收口径：后续不再以“是否存在 `planner shell / routing / events（规划壳层 / 路由 / 事件）`”作为迁移完成标准，而以“最终交互姿态是否已完成单一真相源交接”作为唯一标准。
