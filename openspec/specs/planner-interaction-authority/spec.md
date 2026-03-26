# planner-interaction-authority 规范

## 目的
待定 - 由归档变更 complete-planner-control-handoff 创建。归档后请更新目的。
## 需求
### 需求:系统必须让失败收束仍服从 planner 交互裁判权
系统必须让 validation reject、tool 失败、constraint violation 与 planner runtime 异常等失败收束仍服从 `planner / policy` 的最终交互裁判权；禁止让 `rule planner`、`legacy QA`、`sufficiency gate` 或其他尾部规则在失败时接管最终用户姿态。

#### 场景:失败时仍由 planner 决定用户姿态
- **当** `LLM planner decision` 已被接受但执行阶段返回证据不足、依赖缺失或 citation 不满足等约束
- **那么** 系统必须将这些约束回传给 `planner / policy` 决定最终 `clarify`、`partial_answer` 或 `refuse`，而不得由旧规则链直接接管

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
系统必须在运行 trace 中稳定记录 `final_interaction_authority`、`interaction_decision_source`、`final_user_visible_posture`、`posture_override_forbidden` 与失败收束来源；禁止让一次请求的最终交互姿态无法追溯其唯一来源，也禁止把 validation reject 或运行时异常伪装成旧规则决定。

#### 场景:失败收束来源可追溯
- **当** 一次请求因 validation reject、tool failure 或 runtime exception 而结束
- **那么** trace 中必须能够明确表明最终用户姿态来自 `planner / policy` 或受控结束语义，并记录具体失败来源，而不得显示为 `rule planner` 或旧 QA 尾部改写

### 需求:系统必须将服务级阻断置于单轮交互姿态裁决之上
系统必须将 planner LLM 基础设施未就绪导致的正式服务阻断定义为高于单轮 `execute`、`clarify`、`partial_answer`、`refuse` 与 `delegate` 的服务可用性约束。对于系统级阻断，系统禁止继续声称本轮请求仍由普通 `planner / policy` 交互姿态裁决完成。

#### 场景:服务阻断不伪装成拒答姿态
- **当** 正式聊天入口因 planner LLM 基础设施未就绪而被阻断
- **那么** 运行 trace 与用户可见结果必须明确表达服务级阻断，而不得仅显示为普通 `refuse` 或 `controlled_terminate`

