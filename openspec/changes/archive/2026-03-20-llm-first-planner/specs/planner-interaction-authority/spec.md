## 新增需求

### 需求:系统必须让失败收束仍服从 planner 交互裁判权
系统必须让 validation reject、tool 失败、constraint violation 与 planner runtime 异常等失败收束仍服从 `planner / policy` 的最终交互裁判权；禁止让 `rule planner`、`legacy QA`、`sufficiency gate` 或其他尾部规则在失败时接管最终用户姿态。

#### 场景:失败时仍由 planner 决定用户姿态
- **当** `LLM planner decision` 已被接受但执行阶段返回证据不足、依赖缺失或 citation 不满足等约束
- **那么** 系统必须将这些约束回传给 `planner / policy` 决定最终 `clarify`、`partial_answer` 或 `refuse`，而不得由旧规则链直接接管

## 修改需求

### 需求:系统必须让最终交互姿态可审计
系统必须在运行 trace 中稳定记录 `final_interaction_authority`、`interaction_decision_source`、`final_user_visible_posture`、`posture_override_forbidden` 与失败收束来源；禁止让一次请求的最终交互姿态无法追溯其唯一来源，也禁止把 validation reject 或运行时异常伪装成旧规则决定。

#### 场景:失败收束来源可追溯
- **当** 一次请求因 validation reject、tool failure 或 runtime exception 而结束
- **那么** trace 中必须能够明确表明最终用户姿态来自 `planner / policy` 或受控结束语义，并记录具体失败来源，而不得显示为 `rule planner` 或旧 QA 尾部改写

## 移除需求
