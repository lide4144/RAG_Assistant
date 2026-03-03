## MODIFIED Requirements

### 需求:主题不匹配必须触发不足
当 `top_n evidence` 与问题主题相关性低于门限时，系统必须判定为证据不足，且禁止直接进入 `answer` 决策。对于控制意图轮次，系统必须使用锚定主题查询（`anchor_query` 或等价字段）作为主题匹配输入来源，而非直接使用控制语句本身。

#### 场景:相关性低触发拒答或澄清
- **当** 证据主题与问题主题不匹配且相关性低于门限
- **那么** 系统必须输出 `refuse` 或 `clarify`，并在 `reason` 中说明“主题不匹配/相关性不足”

#### 场景:控制意图场景使用锚定主题做匹配
- **当** 当前轮 `intent_type` 为 `style_control` 且存在 `anchor_query`
- **那么** Gate 的 `topic_match_score_query_used` 必须基于 `anchor_query` 计算，不得基于“用中文回答我”等控制语句计算

