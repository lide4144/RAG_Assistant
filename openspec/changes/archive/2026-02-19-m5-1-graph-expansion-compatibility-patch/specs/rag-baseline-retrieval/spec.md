## 新增需求

## 修改需求

### 需求:检索模式与融合
系统必须在首次检索后对 Top-5 evidence 执行 summary shell 比例检测；当 shell 占比大于 60% 且尚未 retry 时，系统必须最多触发一次 query retry。完成最终一次检索后，系统必须在初检 `top_k` 上执行图扩展召回，并将“初检 + 扩展”候选并入后续证据组织流程。`dense` 模式在 `dense_backend=embedding` 时必须对 query 调用 embedding API，并以 query/doc 的 cosine 相似度排序；`hybrid` 模式必须融合 BM25 与当前 dense backend 分数，且融合前必须先做 min-max normalize。系统输出给图扩展的 seeds 必须包含：`chunk_id`、`score`、`payload.source`（`bm25|dense|hybrid|graph_expand`）、`payload.dense_backend`（`tfidf|embedding`）、`payload.retrieval_mode`（`dense|bm25|hybrid`）。当 `dense_backend=embedding` 时，seeds 还必须包含 `payload.embedding_provider`、`payload.embedding_model`，并允许可选 `payload.embedding_version`。

#### 场景:触发单次 retry
- **当** Top-5 evidence 中 summary shell 占比 > 60%
- **那么** 系统必须移除 `summary/overview/abstract/reporting` 相关 cue words，强制追加已命中的语义意图 cue words 并重新检索一次

#### 场景:retry 次数上限
- **当** 系统已执行一次 retry
- **那么** 同一请求禁止再次触发 retry，且 `query_retry_used` 必须为 true

#### 场景:初检后执行图扩展
- **当** 系统完成最终一次检索并得到初检 `top_k` 候选
- **那么** 系统必须执行 1-hop 图扩展并将合并去重后的候选集合提供给后续证据组织阶段

#### 场景:seeds 元数据完整性
- **当** 系统把初检候选传递给 graph expansion
- **那么** 每个 seed 必须包含 `source`、`dense_backend`、`retrieval_mode`，且在 embedding 后端下必须包含 `embedding_provider` 与 `embedding_model`

### 需求:运行日志必须完整记录 embedding 检索字段
当 `dense_backend=embedding` 或 `embedding.enabled=true` 时，系统必须记录：`embedding_enabled`、`embedding_provider`、`embedding_model`、`embedding_dim`、`embedding_batch_size`、`embedding_cache_enabled`、`embedding_cache_hits`、`embedding_cache_miss`、`embedding_api_calls`、`embedding_query_time_ms`、`dense_score_type`、`hybrid_fusion_weight`。此外，系统必须记录并可序列化：`dense_backend`、`graph_expand_alpha`、`expansion_added_chunks`、`expansion_budget`，用于追踪 graph expansion 兼容补丁行为。

#### 场景:记录 embedding 运行指标
- **当** 用户执行 `python -m app.qa --mode dense|hybrid`
- **那么** 系统输出日志必须包含上述 embedding 字段且字段可序列化

#### 场景:记录图扩展预算与后端
- **当** 系统在初检后执行 graph expansion
- **那么** 运行日志必须记录 `dense_backend`、`graph_expand_alpha`、`expansion_added_chunks` 与 `expansion_budget`

## 移除需求
