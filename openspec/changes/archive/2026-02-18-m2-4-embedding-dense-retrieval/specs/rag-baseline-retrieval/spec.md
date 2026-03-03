## ADDED Requirements

### 需求:Dense backend 必须可配置并默认使用 embedding
系统必须支持 `dense_backend: embedding|tfidf` 配置，默认值必须为 `embedding`。`--mode dense` 必须根据 `dense_backend` 选择实现，且不得改变 CLI 参数语义。

#### 场景:切换 dense backend
- **当** `dense_backend=tfidf`
- **那么** 系统必须回退到 TF-IDF dense，且禁止调用 embedding API

### 需求:运行日志必须完整记录 embedding 检索字段
当 `dense_backend=embedding` 或 `embedding.enabled=true` 时，系统必须记录：`embedding_enabled`、`embedding_provider`、`embedding_model`、`embedding_dim`、`embedding_batch_size`、`embedding_cache_enabled`、`embedding_cache_hits`、`embedding_cache_miss`、`embedding_api_calls`、`embedding_query_time_ms`、`dense_score_type`、`hybrid_fusion_weight`。

#### 场景:记录 embedding 运行指标
- **当** 用户执行 `python -m app.qa --mode dense|hybrid`
- **那么** 系统输出日志必须包含上述 embedding 字段且字段可序列化

## MODIFIED Requirements

### 需求:基础检索索引构建
系统必须基于 `data/processed/chunks_clean.jsonl` 构建 BM25 与向量索引。系统必须使用 `clean_text` 作为索引文本字段，且禁止将 `content_type=watermark` 的 chunk 纳入任一索引。自 M2.4 起，向量索引默认必须为 embedding 向量索引（`data/indexes/vec_index_embed.json`）；当 `dense_backend=tfidf` 时，系统必须允许回退使用 TF-IDF 向量索引作为 baseline。

#### 场景:构建 BM25 与向量索引
- **当** 用户执行索引构建流程并提供 `chunks_clean.jsonl`
- **那么** 系统必须同时产出 BM25 与向量索引，并记录索引条目数

#### 场景:过滤 watermark chunk
- **当** 输入 chunk 的 `content_type` 为 `watermark`
- **那么** 系统必须在 BM25 与向量索引构建阶段都排除该 chunk

### 需求:检索模式与融合
系统必须在首次检索后对 Top-5 evidence 执行 summary shell 比例检测；当 shell 占比大于 60% 且尚未 retry 时，系统必须最多触发一次 query retry。完成最终一次检索后，系统必须在初检 `top_k` 上执行图扩展召回，并将“初检 + 扩展”候选并入后续证据组织流程。`dense` 模式在 `dense_backend=embedding` 时必须对 query 调用 embedding API，并以 query/doc 的 cosine 相似度排序；`hybrid` 模式必须融合 BM25 与当前 dense backend 分数，且融合前必须先做 min-max normalize。

#### 场景:触发单次 retry
- **当** Top-5 evidence 中 summary shell 占比 > 60%
- **那么** 系统必须移除 `summary/overview/abstract/reporting` 相关 cue words，强制追加已命中的语义意图 cue words 并重新检索一次

#### 场景:retry 次数上限
- **当** 系统已执行一次 retry
- **那么** 同一请求禁止再次触发 retry，且 `query_retry_used` 必须为 true

#### 场景:初检后执行图扩展
- **当** 系统完成最终一次检索并得到初检 `top_k` 候选
- **那么** 系统必须执行 1-hop 图扩展并将合并去重后的候选集合提供给后续证据组织阶段

### 需求:最小 QA CLI 输出
系统必须提供命令 `python -m app.qa --q "<question>" --mode dense|bm25|hybrid`。除既有字段外，系统还必须在运行输出中记录：`calibrated_query`、`calibration_reason`、`query_retry_used`、`query_retry_reason`（若触发），并且必须输出 `answer_citations` 与 `output_warnings`。当 `dense_backend=embedding` 时，`dense_score_type` 必须为 `cosine`。

#### 场景:校准与输出治理字段完整落盘
- **当** 用户执行 QA CLI 并完成检索与回答生成
- **那么** 输出与运行记录必须包含校准字段、回答 citation 字段与 warning 字段，且字段可序列化
