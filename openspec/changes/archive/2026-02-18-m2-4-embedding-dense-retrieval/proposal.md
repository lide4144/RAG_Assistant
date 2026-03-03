## 为什么

当前系统把 TF-IDF 余弦当作 dense 检索，无法稳定覆盖“词不重合但语义相关”的问题，导致 Hybrid RAG 的语义召回上限受限。M2.4 需要把 dense 升级为真实 embedding 向量检索，并在不破坏既有 M2/M2.1/M2.2/M2.3 输出结构的前提下，提供可缓存、可复现、可配置的外部 API 向量能力。

## 变更内容

- 新增基于外部 embedding API（默认 SiliconFlow）的向量索引构建流程，输出 `data/indexes/vec_index_embed.json`。
- 新增 embedding 配置段（provider/model/base_url/batch_size/normalize/cache 等）及 `dense_backend: embedding|tfidf`，默认 `embedding`。
- 将 `--mode dense` 升级为根据 `dense_backend` 选择 embedding dense 或 TF-IDF baseline。
- 将 `--mode hybrid` 的 dense 分数来源切换为“当前 dense backend”，并在融合前执行 min-max normalize。
- 保留现有 content_type 权重策略与 graph expansion 行为，embedding 检索后仍执行图扩展；扩展候选无向量分数时按 seed 衰减继承。
- 新增完整 embedding 运行日志字段（provider/model/dim/batch/cache/api 调用/查询耗时/score type 等）。
- 新增 M2.4 评估记录产物 `reports/m2_4_embedding_upgrade.md`，覆盖语义匹配、hybrid 改善、构建耗时和缓存命中率。
- **BREAKING**：`dense` 的默认语义从“TF-IDF dense”变为“embedding dense”；但通过 `dense_backend: tfidf` 提供后向兼容回退。

## 功能 (Capabilities)

### 新增功能
- `embedding-indexing-and-cache`: 定义 embedding 索引构建、批量调用、失败重试、L2 归一化与 chunk 级缓存的行为契约。

### 修改功能
- `rag-baseline-retrieval`: 调整 dense/hybrid 检索语义与 backend 选择逻辑，补充 embedding 日志字段与兼容策略。
- `graph-expansion-retrieval`: 明确 embedding 检索后的图扩展兼容规则，以及扩展候选缺失 dense 分数时的继承衰减策略。

## 影响

- 受影响代码：索引构建模块、检索打分模块、混合融合模块、运行日志记录模块、配置加载模块、CLI 行为实现。
- 受影响数据文件：`data/indexes/vec_index_embed.json`、`data/indexes/embedding_cache.jsonl`、`reports/m2_4_embedding_upgrade.md`。
- 外部依赖：embedding provider HTTP API（默认 SiliconFlow）与对应 API Key 环境变量。
- 兼容性影响：对用户 CLI 参数无变更；通过配置保障 dense 行为的后向兼容与消融实验可复现性。
