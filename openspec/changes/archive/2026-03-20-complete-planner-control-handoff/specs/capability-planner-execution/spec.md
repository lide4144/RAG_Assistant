## MODIFIED Requirements

### 需求:系统必须将 planner 决策与 QA 交互姿态解耦
系统必须将“是否澄清、是否给部分回答、是否拒答”的顶层交互姿态定义为 `planner / policy（规划器 / 策略层）` 的唯一决策结果，而 deterministic kernel（确定性内核）仅负责输出证据、依赖、引用或执行约束信号；禁止继续由 `qa.py`、`sufficiency gate（充分性门控）`、`evidence gate（证据门）` 或其他尾部规则在 planner 决策之后独立重写本轮最终交互姿态。系统必须通过统一的 `constraints envelope（约束信封）` 将底层阻塞信息回传给 planner，再由 planner 统一决定最终用户可见姿态。

#### 场景:kernel 输出约束信号但不独占最终姿态
- **当** deterministic kernel（确定性内核）判定当前请求证据不足、依赖不满足或引用不合法
- **那么** kernel 必须输出结构化约束信号供 `planner / policy（规划器 / 策略层）` 消费，而不是绕过顶层 planner 直接决定最终用户姿态

#### 场景:planner 成为用户交互姿态真相源
- **当** 本轮请求最终以 `clarify（澄清）`、`partial_answer（部分回答）` 或 `refuse（拒答）` 收束
- **那么** 运行 trace 必须能表明该姿态来自 `planner / policy（规划器 / 策略层）` 的最终决策，且不得存在 `legacy qa tail override（旧问答尾部改写）`

### 需求:系统必须提供 planner 与执行器观测字段
系统必须在运行 trace 中输出 planner runtime（规划运行时）、tool execution（工具执行）与最终交互姿态的观测字段，至少包含 `planner_used（是否使用规划器）`、`planner_source（规划器来源）`、`decision_result（决策结果）`、`primary_capability（主能力）`、`selected_path（选中路径）`、`execution_trace（执行轨迹）`、`planner_fallback（规划器回退）`、`tool_fallback（工具回退）`、`final_interaction_authority（最终交互裁判）`、`interaction_decision_source（交互决策来源）`、`final_user_visible_posture（最终用户可见姿态）` 与 `kernel_constraint_summary（内核约束摘要）`。禁止仅记录 planner 选择而无法还原最终交互姿态由谁决定。

#### 场景:顶层决策与最终姿态共同可审计
- **当** 系统经由 planner runtime（规划运行时）完成一次本地执行、委托、澄清或回退
- **那么** trace 中必须同时记录顶层 planner 决策、底层执行结果与最终用户可见姿态来源

#### 场景:被禁止的尾部改写可识别
- **当** 某个下游组件试图在 planner 决策之后重新写入最终姿态
- **那么** 系统必须将其标记为违反本规范的错误状态，并在 trace 中可识别
