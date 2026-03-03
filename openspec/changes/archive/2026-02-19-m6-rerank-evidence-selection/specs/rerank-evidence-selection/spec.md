## 新增需求

### 需求:候选输入字段契约必须完整
系统在 rerank 前必须接收 `candidates` 与 `query`；每个 candidate 必须包含 `score_retrieval`、`payload.source`、`payload.dense_backend`。当 `payload.dense_backend=embedding` 时，candidate 还必须包含 `payload.embedding_provider` 与 `payload.embedding_model`。

#### 场景:输入字段完整时允许进入 rerank
- **当** 候选集合中每条记录都满足字段契约
- **那么** 系统必须执行 rerank，并保留每条 candidate 的原有 payload 字段

#### 场景:embedding 元数据缺失时触发约束
- **当** 某条 candidate 的 `payload.dense_backend=embedding` 且缺失 `embedding_provider` 或 `embedding_model`
- **那么** 系统必须将该问题标记为输入不满足契约，并禁止把该条记录作为有效 rerank 输入

### 需求:rerank 输出必须保留检索分并新增重排分
系统必须在 rerank 结果中为每条入选 evidence 生成 `score_rerank`，并必须保留原始 `score_retrieval` 以支持前后对比实验。

#### 场景:生成 top_n evidence
- **当** rerank 对候选完成打分
- **那么** 系统必须按 `score_rerank` 降序选择 top_n evidence，且每条结果同时包含 `score_retrieval` 与 `score_rerank`

#### 场景:未显式配置 top_n
- **当** 用户未配置 rerank 的输出条数
- **那么** 系统必须使用默认 `top_n=8`

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

## 修改需求

## 移除需求
