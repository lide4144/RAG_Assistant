# rerank-evidence-selection 规范

## 目的
待定 - 由归档变更 m6-rerank-evidence-selection 创建。归档后请更新目的。
## 需求
### 需求:候选输入字段契约必须完整
系统在 rerank 前必须接收 `candidates` 与 `query`；每个 candidate 必须包含 `score_retrieval`、`payload.source`、`payload.dense_backend`。当 `payload.dense_backend=embedding` 时，candidate 还必须包含 `payload.embedding_provider` 与 `payload.embedding_model`。

#### 场景:输入字段完整时允许进入 rerank
- **当** 候选集合中每条记录都满足字段契约
- **那么** 系统必须执行 rerank，并保留每条 candidate 的原有 payload 字段

#### 场景:embedding 元数据缺失时触发约束
- **当** 某条 candidate 的 `payload.dense_backend=embedding` 且缺失 `embedding_provider` 或 `embedding_model`
- **那么** 系统必须将该问题标记为输入不满足契约，并禁止把该条记录作为有效 rerank 输入

### 需求:rerank 输出必须保留检索分并新增重排分
系统必须在 rerank 成功与失败两种路径中都输出兼容字段：每条 evidence 必须包含 `score_retrieval` 与 `score_rerank`。当 rerank 失败并触发静默穿透时，系统必须用可解释策略生成 `score_rerank`（默认等于 `score_retrieval`），以保证下游结构兼容。

#### 场景:静默穿透仍返回兼容分数字段
- **当** rerank 调用失败并启用穿透
- **那么** 每条候选必须仍包含 `score_rerank` 字段，且下游 `qa` 流程不得因字段缺失失败

### 需求:rerank 阶段禁止改写 dense backend 语义
系统在 rerank 前后必须保持 `payload.dense_backend` 不变，禁止在 rerank 阶段把 `tfidf` 改写为 `embedding` 或反向改写。

#### 场景:输出字段透传
- **当** candidate 进入 rerank 并被输出
- **那么** 该 candidate 的 `payload.dense_backend` 必须与输入保持一致

### 需求:运行日志必须记录 rerank 指标
系统必须在 runs 日志中记录 `rerank_top_n`、`rerank_score_distribution`、`dense_backend`，用于验证 rerank 行为与分布稳定性。

#### 场景:落盘 rerank 指标
- **当** 一次 QA 运行完成 rerank 阶段
- **那么** 对应 run_trace 或等效日志必须包含上述三个字段且字段可序列化

### 需求:系统必须支持 SiliconFlow Qwen3-Reranker-8B 作为可选后端
系统必须允许将 SiliconFlow 的 `Qwen/Qwen3-Reranker-8B` 配置为 reranker provider/model，并通过统一接口调用。

#### 场景:启用指定模型
- **当** 配置指定 provider 为 SiliconFlow 且 model 为 `Qwen/Qwen3-Reranker-8B`
- **那么** 系统必须使用该模型执行 rerank，并输出可用的 `score_rerank`

### 需求:Rerank API 失败时必须静默穿透
当 rerank API 调用发生超时、网络错误或 5xx 时，系统必须跳过重排并直接返回上游检索序；系统必须记录 `rerank_fallback_to_retrieval` 或等价标记用于观测。

#### 场景:超时触发穿透
- **当** rerank 请求超过 `timeout_ms`
- **那么** 系统必须直接返回上游候选顺序并标记 `used_fallback=true`

