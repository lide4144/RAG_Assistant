## 1. 配置与接口准备

- [x] 1.1 在 `configs/default.yaml` 新增 `embedding` 配置段（enabled/provider/base_url/model/api_key_env/batch_size/normalize/cache_enabled/cache_path）
- [x] 1.2 新增 `dense_backend: embedding|tfidf` 配置并设默认值为 `embedding`
- [x] 1.3 实现 embedding provider 客户端与配置加载校验（含 API Key 环境变量读取）

## 2. Embedding 索引构建与缓存

- [x] 2.1 在索引构建流程中按 `suppressed=false`、`content_type!=watermark`、`clean_text` 过滤输入 chunk
- [x] 2.2 实现 embedding 批量请求（按 `batch_size`）及单条失败最多 2 次重试
- [x] 2.3 实现 `embedding_cache.jsonl` 读写与 `(chunk_id, model)` 命中逻辑，统计 cache hit/miss
- [x] 2.4 生成 `data/indexes/vec_index_embed.json`，写入 provider/model/dim 与 docs 向量记录
- [x] 2.5 当 `normalize=true` 时实现 doc 向量 L2 normalize，并增加维度一致性校验

## 3. Dense/Hybrid 检索升级与兼容

- [x] 3.1 将 `--mode dense` 切换为按 `dense_backend` 选择 embedding cosine 或 TF-IDF dense
- [x] 3.2 在 embedding dense 路径实现 query embedding（含耗时统计）与 cosine 排序
- [x] 3.3 在 hybrid 路径使用 BM25 + 当前 dense 分数，融合前执行 min-max normalize
- [x] 3.4 保留并验证 M2.1 的 content_type 权重策略与条件放行逻辑在 embedding 路径继续生效

## 4. 图扩展兼容处理

- [x] 4.1 保持 embedding 检索后调用 `expand_candidates_with_graph()`
- [x] 4.2 对扩展候选缺失 dense 分数时实现 seed score 继承衰减（adjacent=0.97，entity=0.94）
- [x] 4.3 禁止为图扩展新增候选二次调用 embedding API，并补充对应断言/测试

## 5. 日志与输出一致性

- [x] 5.1 在 QA 运行日志中落盘完整 embedding 字段（enabled/provider/model/dim/batch/cache/hit/miss/api_calls/query_time_ms/dense_score_type/hybrid_fusion_weight）
- [x] 5.2 验证 `papers_ranked`、`evidence_grouped`、`answer_citations` 与既有输出结构保持兼容
- [x] 5.3 确保 `dense_backend=tfidf` 时日志与行为正确回退且不调用外部 embedding API

## 6. 验收与报告

- [x] 6.1 执行 Dense 可运行验收（20 问）并确认候选非空及日志完整
- [x] 6.2 执行 bm25/dense/hybrid 对比并记录 hybrid 可见差异样例
- [x] 6.3 完成 5 组语义匹配测试（词不重合）并对比 TF-IDF baseline
- [x] 6.4 执行两轮索引构建，统计 cache 首轮 miss 与次轮 >90% hits
- [x] 6.5 生成 `reports/m2_4_embedding_upgrade.md`（语义测试、dense 对比、hybrid 改善、耗时统计、缓存命中率）
