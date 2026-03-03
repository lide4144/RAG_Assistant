## 新增需求

### 需求:候选进入证据组织前必须经过可配置重排序
系统在完成“初检 + 图扩展”候选汇总后，必须先执行 rerank 再进入证据组织流程；当 rerank 被显式关闭时，系统必须回退为按 `score_retrieval` 排序的直通路径，并保持输出结构兼容。

#### 场景:默认执行 rerank 后再分配证据
- **当** 系统完成最终一次检索并得到候选集合
- **那么** 系统必须先产生 `score_rerank` 并按 rerank 结果截断 top_n，然后再执行后续 evidence 组织

#### 场景:rerank 关闭时安全回退
- **当** rerank 配置为 disabled 或运行时不可用
- **那么** 系统必须使用 `score_retrieval` 排序回退，且不得改变 `dense_backend` 与候选 payload 语义

## 修改需求

### 需求:运行日志必须完整记录 embedding 检索字段
当 `dense_backend=embedding` 或 `embedding.enabled=true` 时，系统必须记录：`embedding_enabled`、`embedding_provider`、`embedding_model`、`embedding_dim`、`embedding_batch_size`、`embedding_cache_enabled`、`embedding_cache_hits`、`embedding_cache_miss`、`embedding_api_calls`、`embedding_query_time_ms`、`dense_score_type`、`hybrid_fusion_weight`。此外，系统必须记录并可序列化：`dense_backend`、`graph_expand_alpha`、`expansion_added_chunks`、`expansion_budget`、`rerank_top_n`、`rerank_score_distribution`，用于追踪 graph expansion 与 rerank 行为。

#### 场景:记录 embedding 运行指标
- **当** 用户执行 `python -m app.qa --mode dense|hybrid`
- **那么** 输出日志必须包含上述 embedding 字段且字段可序列化

#### 场景:记录图扩展预算与后端
- **当** 系统在初检后执行 graph expansion
- **那么** 运行日志必须记录 `dense_backend`、`graph_expand_alpha`、`expansion_added_chunks` 与 `expansion_budget`

#### 场景:记录 rerank 分布与截断规模
- **当** 系统在候选阶段执行 rerank
- **那么** 运行日志必须记录 `rerank_top_n` 与 `rerank_score_distribution`，并可用于 rerank 前后对比

## 移除需求
