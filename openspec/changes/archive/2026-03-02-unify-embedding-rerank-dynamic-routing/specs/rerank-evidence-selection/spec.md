## MODIFIED Requirements

### 需求:rerank 输出必须保留检索分并新增重排分
系统必须在 rerank 成功与失败两种路径中都输出兼容字段：每条 evidence 必须包含 `score_retrieval` 与 `score_rerank`。当 rerank 失败并触发静默穿透时，系统必须用可解释策略生成 `score_rerank`（默认等于 `score_retrieval`），以保证下游结构兼容。

#### 场景:静默穿透仍返回兼容分数字段
- **当** rerank 调用失败并启用穿透
- **那么** 每条候选必须仍包含 `score_rerank` 字段，且下游 `qa` 流程不得因字段缺失失败

## ADDED Requirements

### 需求:Rerank API 失败时必须静默穿透
当 rerank API 调用发生超时、网络错误或 5xx 时，系统必须跳过重排并直接返回上游检索序；系统必须记录 `rerank_fallback_to_retrieval` 或等价标记用于观测。

#### 场景:超时触发穿透
- **当** rerank 请求超过 `timeout_ms`
- **那么** 系统必须直接返回上游候选顺序并标记 `used_fallback=true`

