## MODIFIED Requirements

### 需求:Sufficiency Gate 决策输出
系统必须在最终回答前基于 `question` 与 `top_n evidence` 产出单一决策对象，字段至少包含 `decision` 与 `reason`；其中 `decision` 必须为 `answer`、`refuse`、`clarify` 三者之一。当 `decision=clarify` 时，系统必须额外输出 `clarify_questions`，且数量必须为 1~2 个。系统必须输出可供 UI 审查的告警字段（含 `output_warnings` 或等价结构），并确保 `reason` 与告警字段可序列化且可直接展示。

#### 场景:输出结构合法
- **当** 系统收到一次问答请求并完成证据聚合
- **那么** 系统必须返回包含 `decision` 与 `reason` 的决策对象，且 `decision` 取值仅限 `answer/refuse/clarify`

#### 场景:clarify 输出问题数量受控
- **当** Sufficiency Gate 判定为 `clarify`
- **那么** 输出必须包含 `clarify_questions`，且问题数量必须为 1 或 2

#### 场景:降级原因可视化字段完整
- **当** Sufficiency Gate 判定为 `refuse` 或 `clarify`
- **那么** 输出必须包含可展示的 `reason` 与告警字段，供 UI 以高亮方式展示
