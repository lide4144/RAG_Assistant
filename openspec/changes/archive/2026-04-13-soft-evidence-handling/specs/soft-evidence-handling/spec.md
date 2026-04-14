# Soft Evidence Handling 规范

## 目的
定义系统在证据不足时的软性处理机制，允许结合模型知识给出"诚实的不确定回答"，同时通过明确标注帮助用户理解回答的可信度。

## 新增需求

### 需求:系统必须在证据不足时使用模型知识补充回答
当 Sufficiency Gate 判定证据不足但至少存在 1 条证据时，系统必须允许使用模型知识补充回答，而非直接拒绝。回答必须明确标注内容来源，区分"知识库证据"和"模型知识"。

#### 场景:1条证据时触发模型知识补充
- **当** Sufficiency Gate 判定证据数量为 1 条（满足最低阈值）
- **那么** 系统必须进入 `low_confidence_with_model_knowledge` 回答模式
- **并且** 必须生成包含内联来源标注的回答
- **并且** 必须在 trace 中标记 `answer_confidence.level` 为 `"low"`

#### 场景:0条证据时仍然拒绝
- **当** Sufficiency Gate 判定证据数量为 0 条
- **那么** 系统必须保持 `refuse` 决策，不得使用模型知识
- **并且** 必须返回标准拒绝提示

### 需求:系统必须使用内联标注区分内容来源
系统必须在生成的回答中使用内联标注格式，明确区分来自知识库证据的内容和来自模型知识的内容。标注格式必须为 `[📄 chunk_id]`（知识库）或 `[🤖 模型推测]`（模型知识）。

#### 场景:知识库内容标注
- **当** 回答中的某句内容基于检索到的证据
- **那么** 该句末尾必须附加 `[📄 {chunk_id}]` 标注
- **并且** chunk_id 必须对应实际存在的证据项

#### 场景:模型知识内容标注
- **当** 回答中的某句内容基于模型训练知识（非知识库证据）
- **那么** 该句末尾必须附加 `[🤖 模型推测]` 标注
- **并且** 该标注前必须有明显的内容分隔（如换行或句号）

### 需求:系统必须返回结构化的置信度提示数据
系统必须在 API 返回的 trace 中新增 `answer_confidence` 和 `honesty_disclosure` 字段，供前端渲染置信度提示。

#### 场景:低置信度回答的完整数据结构
- **当** 系统进入 `low_confidence_with_model_knowledge` 模式
- **那么** trace 必须包含 `answer_confidence` 对象，包含：
  - `level`: "low" | "medium" | "high"
  - `source`: "model_knowledge_supplemented" | "evidence_only"
  - `evidence_coverage`: 0.0~1.0 的浮点数
  - `uncertainty_reasons`: 字符串数组
- **并且** trace 必须包含 `honesty_disclosure` 对象，包含：
  - `should_show`: true
  - `type`: "insufficient_evidence"
  - `severity`: "warning"
  - `title`: 提示标题
  - `message`: 提示正文
  - `evidence_stats`: 证据统计
  - `suggested_actions`: 建议操作数组

### 需求:系统必须记录用户对低置信度提示的偏好
系统必须在 session state 中记录用户是否选择"不再提示"低置信度警告，避免重复打扰用户。

#### 场景:用户选择不再提示
- **当** 用户在前端点击"不再提示"按钮
- **那么** 系统必须在 session 中设置 `user_honesty_preferences.hide_low_confidence_warnings = true`
- **并且** 该设置必须在同一会话的后续请求中生效
- **并且** 新会话或 24 小时后自动重置

#### 场景:根据用户偏好控制提示显示
- **当** 系统判定需要显示低置信度提示
- **并且** `user_honesty_preferences.hide_low_confidence_warnings` 为 true
- **那么** 系统必须设置 `honesty_disclosure.should_show = false`
- **但是** `answer_confidence` 数据仍然必须返回（供前端自行决定）

### 需求:系统必须保持向后兼容
所有新增字段必须是可选的，现有前端代码必须能够忽略新字段而正常工作。

#### 场景:旧版前端忽略新字段
- **当** 使用不支持新功能的前端调用 API
- **那么** 系统必须正常返回所有原有字段
- **并且** 新增字段不得影响现有字段的值
- **并且** `answer` 字段的格式必须保持兼容（只是多了内联标注）
