# rag-baseline-retrieval 规范

## 目的
待定 - 由归档变更 m2-rag-baseline-retrieval 创建。归档后请更新目的。
## 需求
### 需求:基础检索索引构建
系统必须基于 `data/processed/chunks_clean.jsonl` 构建 BM25 与向量索引。系统必须使用 `clean_text` 作为索引文本字段，且禁止将 `content_type=watermark` 的 chunk 纳入任一索引。自 M2.4 起，向量索引默认必须为 embedding 向量索引（`data/indexes/vec_index_embed.json`）；当 `dense_backend=tfidf` 时，系统必须允许回退使用 TF-IDF 向量索引作为 baseline。

#### 场景:构建 BM25 与向量索引
- **当** 用户执行索引构建流程并提供 `chunks_clean.jsonl`
- **那么** 系统必须同时产出 BM25 与向量索引，并记录索引条目数

#### 场景:过滤 watermark chunk
- **当** 输入 chunk 的 `content_type` 为 `watermark`
- **那么** 系统必须在 BM25 与向量索引构建阶段都排除该 chunk

### 需求:检索模式与融合
系统必须支持“三层检索”默认路径：先基于 `paper_summary` 进行候选文档粗召回，再对结构类问题优先执行 section-aware retrieval，最后在候选文档或候选章节范围内执行 chunk 检索与重排；系统必须支持在摘要层或结构层不可用时回退到原有 chunk 全库检索。

#### 场景:摘要层命中后进入候选文档精检索
- **当** 查询在 `paper_summary` 层返回候选文档
- **那么** 系统必须仅在候选文档范围执行 chunk 检索与重排并产出证据

#### 场景:摘要层不可用时安全回退
- **当** `paper_summary` 索引不可用或召回为空
- **那么** 系统必须回退至原有 chunk 检索路径并保持流程可用

#### 场景:结构层命中后进入章节精检索
- **当** 查询命中结构类意图且结构索引可用
- **那么** 系统必须先执行 section retrieval，再基于章节候选补充 chunk 证据并进入后续重排

#### 场景:结构层不可用时安全回退
- **当** 结构索引不可用、结构解析状态非 `ready` 或 section retrieval 为空
- **那么** 系统必须回退至 chunk 检索路径，并记录结构回退原因

### 需求:检索链路必须支持结构类问题路由
系统必须识别论文结构类问题，并在命中时优先使用章节树索引执行 structure-aware retrieval；当未命中结构类意图时，系统必须继续沿用既有摘要层与 chunk 层检索路径。

#### 场景:结构类问题进入 section route
- **当** 用户问题命中“章节/目录/结构/第几节”等结构类意图
- **那么** 系统必须将检索路由记录为 `section`，并优先使用 section index 召回候选

#### 场景:普通问题保持既有主路径
- **当** 用户问题不命中结构类意图
- **那么** 系统必须继续使用既有摘要层与 chunk 层检索，不得强制经过 section route

### 需求:结构检索必须输出可观测字段
当一次查询使用或尝试使用 structure-aware retrieval 时，系统必须记录结构检索观测字段，至少包括 `retrieval_route`、`structure_parse_status`、`section_candidates_count`、`section_route_used` 与 `structure_route_fallback`。

#### 场景:结构检索字段可追踪
- **当** 一次 QA 请求结束
- **那么** 运行日志与 QA 输出必须包含上述结构检索字段且字段可序列化

### 需求:section 候选必须补充 chunk 级证据
当 structure-aware retrieval 命中 section 候选时，系统必须将 section 关联 chunk 纳入候选组织、重排或证据分配流程。系统禁止只返回 section 标题而不补充 chunk 证据。

#### 场景:section 命中后补充 chunk evidence
- **当** section retrieval 返回章节候选
- **那么** 系统必须将该 section 的关联 chunk 纳入 evidence 组织，并保证最终 citation 仍指向 chunk

### 需求:最小 QA CLI 输出
系统必须在 QA 输出中记录双层检索观测字段（至少包含摘要召回是否启用、候选文档数量、是否触发回退），并新增语义匹配观测字段（至少包含 embedding 模型标识、相似度分数、策略档位）。

#### 场景:双层检索观测字段落盘
- **当** 一次 QA 请求完成
- **那么** 输出必须包含双层检索与语义匹配观测字段且字段可序列化

### 需求:证据引用来源约束
系统回答中的最终引用必须来自 chunk 级证据集合，禁止直接使用 `paper_summary` 文本作为 `answer_citations` 的事实来源。

#### 场景:摘要层仅用于召回与组织
- **当** 回答包含 citation
- **那么** citation 必须映射到 chunk 证据项而非摘要记录

### 需求:M2 最小验收
系统必须满足 M2 基线验收：dense 与 bm25 都能返回 top-k，hybrid 能返回融合结果；并对至少 30 个自制问题可在 evidence 中找到相关段落（主观评审）。在 M3 中，接入 rewrite 后 Recall@k 主观效果相较未改写不得下降，且至少 10 个问题 evidence 相关性应更高。

#### 场景:检索模式验收
- **当** 对同一问题分别执行 `dense`、`bm25`、`hybrid`
- **那么** 系统必须在三种模式下都返回非空候选，且 `hybrid` 返回融合排序结果

#### 场景:M3 对比评估
- **当** 在同一 30 问题集合上比较“改写前”与“改写后”
- **那么** 主观 Recall@k 不得下降，且至少 10 个问题 evidence 更相关

### 需求:summary shell 识别规则
系统必须支持 summary shell 识别规则，至少覆盖 `In summary`、`SUMMARY OF`、`Reporting summary`、`This paper: • introduces`、`In this survey paper` 等模式，用于计算 Top-5 shell 占比。

#### 场景:计算 shell 占比
- **当** 首次检索得到 Top-5 evidence
- **那么** 系统必须计算并记录 shell 占比，以支持是否触发 retry 的判定

### 需求:Dense backend 必须可配置并默认使用 embedding
系统必须支持 `dense_backend: embedding|tfidf` 配置，默认值必须为 `embedding`。当 `dense_backend=embedding` 且 embedding stage 不可用（例如密钥缺失、连通失败、维度不一致）时，系统必须自动降级到 `tfidf` 路径并保持 CLI/接口语义不变。

#### 场景:embedding 不可用时自动回退
- **当** 用户以 `--mode dense|hybrid` 运行且 embedding stage 返回不可用
- **那么** 系统必须回退到 TF-IDF 检索路径并返回可用候选

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

### 需求:候选进入证据组织前必须经过可配置重排序
系统在完成“初检 + 图扩展”候选汇总后，必须先执行 rerank 再进入证据组织流程；当 rerank 被显式关闭时，系统必须回退为按 `score_retrieval` 排序的直通路径，并保持输出结构兼容。

#### 场景:默认执行 rerank 后再分配证据
- **当** 系统完成最终一次检索并得到候选集合
- **那么** 系统必须先产生 `score_rerank` 并按 rerank 结果截断 top_n，然后再执行后续 evidence 组织

#### 场景:rerank 关闭时安全回退
- **当** rerank 配置为 disabled 或运行时不可用
- **那么** 系统必须使用 `score_retrieval` 排序回退，且不得改变 `dense_backend` 与候选 payload 语义

### 需求:语义主题匹配必须使用轻量 embedding 相似度
系统在证据充分性相关的主题匹配阶段必须使用轻量 embedding 余弦相似度，禁止将纯 Token Overlap 作为唯一主题匹配依据。

#### 场景:中英文混杂语义匹配
- **当** 用户中文提问且候选证据主要为英文表达
- **那么** 系统必须通过语义相似度正确识别主题相关证据

#### 场景:同义表达匹配
- **当** 用户问题与证据使用不同同义词表达相同概念
- **那么** 系统必须维持可接受的语义匹配分数并避免误判为主题不匹配

### 需求:检索链路必须记录 embedding 降级原因
当检索链路从 embedding 回退到词频检索时，系统必须在运行日志记录降级原因（至少区分 `missing_api_key`、`network_error`、`timeout`、`dimension_mismatch`）与是否成功回退。

#### 场景:降级原因可追踪
- **当** 一次查询发生 embedding 回退
- **那么** 运行日志必须包含降级原因分类与回退结果字段，且字段可序列化
