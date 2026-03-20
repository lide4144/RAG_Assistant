## ADDED Requirements

### 需求:系统必须定义最终交互姿态的唯一裁判
系统必须将 `planner / policy（规划器 / 策略层）` 定义为本轮请求最终用户交互姿态的唯一裁判。最终交互姿态至少包括 `execute（执行）`、`clarify（澄清）`、`partial_answer（部分回答）`、`refuse（拒答）` 与 `delegate（委托）`。禁止让 `kernel / qa（内核 / 问答链）`、`sufficiency gate（充分性门控）`、`evidence gate（证据门）` 或任何尾部规则在 planner 决策之后再次独立改写最终用户姿态。

#### 场景:最终姿态由 planner 决定
- **当** 一次请求经过顶层 planner runtime（规划运行时）并产生 `planner decision（规划决策）`
- **那么** 系统必须由 `planner / policy（规划器 / 策略层）` 输出唯一的最终用户交互姿态，且不得由下游组件再次改写

### 需求:系统必须区分交互决策与执行约束
系统必须将 `interaction decision（交互决策）` 与 `execution constraints（执行约束）` 显式分离。底层执行链可以返回证据、引用、依赖、空结果、短路和安全阻断等约束信号，但禁止将这些约束直接等同为最终 `clarify / refuse（澄清 / 拒答）` 决定；系统必须由 `planner / policy（规划器 / 策略层）` 消费这些约束后统一输出最终用户姿态。

#### 场景:底层约束不直接等于拒答
- **当** 底层执行链返回“证据不足”或“引用不合法”等约束
- **那么** 系统必须先将其作为约束信号提供给 `planner / policy（规划器 / 策略层）`，而不是由底层组件直接向用户输出最终拒答

### 需求:系统必须让最终交互姿态可审计
系统必须在运行 trace（运行追踪）中稳定记录 `final_interaction_authority（最终交互裁判）`、`interaction_decision_source（交互决策来源）`、`final_user_visible_posture（最终用户可见姿态）` 与 `posture_override_forbidden（是否发生被禁止的尾部改写）`。禁止让一次请求的最终交互姿态无法追溯其唯一来源。

#### 场景:trace 可证明交互裁判唯一
- **当** 一次请求最终以 `clarify（澄清）`、`partial_answer（部分回答）` 或 `refuse（拒答）` 收束
- **那么** trace 中必须能够明确表明该姿态由 `planner / policy（规划器 / 策略层）` 决定，且 `posture_override_forbidden` 不得为真
