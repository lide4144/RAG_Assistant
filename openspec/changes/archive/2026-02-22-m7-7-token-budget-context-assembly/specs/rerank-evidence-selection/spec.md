## MODIFIED Requirements

### 需求:rerank 输出必须保留检索分并新增重排分
系统必须在 rerank 结果中为每条入选 evidence 生成 `score_rerank`，并必须保留原始 `score_retrieval` 以支持前后对比实验。进入预算裁剪阶段时，系统必须基于 `payload.source` 与 `score_rerank` 执行证据裁剪优先级：优先丢弃 `payload.source=graph_expand` 且 `score_rerank` 低分的 chunk，并优先保留 `payload.source` 为 `bm25` 或 `dense` 的高分证据。

#### 场景:生成 top_n evidence
- **当** rerank 对候选完成打分
- **那么** 系统必须按 `score_rerank` 降序选择 top_n evidence，且每条结果同时包含 `score_retrieval` 与 `score_rerank`

#### 场景:未显式配置 top_n
- **当** 用户未配置 rerank 的输出条数
- **那么** 系统必须使用默认 `top_n=8`

#### 场景:预算裁剪时保留核心来源证据
- **当** 上下文预算超限且需要裁剪 evidence
- **那么** 系统必须先移除低分 `graph_expand` 证据，并在可行范围内保留高分 `bm25/dense` 证据
