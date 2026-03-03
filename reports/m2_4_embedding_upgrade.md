# M2.4 Embedding Upgrade Report

## 评估范围
- 本轮按“分批可复现”方式完成验收，评估摘要在 `reports/m2_4_eval_summary.json`。
- 为控制外部 API 时延与失败重试成本，本次批量验收使用 300 chunk 样本集（`scope: sample_300`）。

## 1) 5 个语义匹配测试对比
来源：`acceptance_6_3_semantic5`

- Q1 `这项工作的主要创新点是什么？`
  - Embedding Top3: `35bf14e7f4c2:00110`, `35bf14e7f4c2:00101`, `3226d0151323:00059`
  - TF-IDF Top3: `35bf14e7f4c2:00111`, `35bf14e7f4c2:00092`, `1a5b25a5e857:00045`
  - 结果：Top3 不同
- Q2 `在该研究中，方法有效性如何验证？`（替换原“作者如何验证方法有效性？”）
  - Embedding Top3: `35bf14e7f4c2:00119`, `35bf14e7f4c2:00117`, `3226d0151323:00017`
  - TF-IDF: 空
  - 结果：Embedding 命中、TF-IDF 未命中
  - 说明：替换后问题为 `scope_mode=open`，不再触发 `clarify_scope`
- Q3 `研究报告了哪些关键指标？`
  - Embedding Top3: `35bf14e7f4c2:00117`, `35bf14e7f4c2:00090`, `3226d0151323:00018`
  - TF-IDF Top3: `35bf14e7f4c2:00062`, `35bf14e7f4c2:00056`, `1a0a22c1909a:00023`
  - 结果：Top3 不同
- Q4 `文中提到了哪些实验设计细节？`
  - Embedding Top3: `35bf14e7f4c2:00090`, `35bf14e7f4c2:00110`, `1a0a22c1909a:00016`
  - TF-IDF: 空
  - 结果：Embedding 命中、TF-IDF 未命中
- Q5 `论文讨论了哪些潜在风险和限制？`
  - Embedding Top3: `3226d0151323:00053`, `3226d0151323:00050`, `35bf14e7f4c2:00125`
  - TF-IDF Top3: `35bf14e7f4c2:00125`, `35bf14e7f4c2:00016`, `3226d0151323:00050`
  - 结果：Top3 不同

## 2) dense vs TF-IDF 对比（最小可复现）
- 运行记录：
  - Embedding dense：`runs/20260218_154454_01`
  - TF-IDF dense：`runs/20260218_154456`, `runs/20260218_154457_01`, `runs/20260218_154458_01`, `runs/20260218_154459_01`
- 结论：多组查询 Top 证据集合出现差异，且存在 Embedding 命中而 TF-IDF 未命中的样例（Q4）。

## 3) hybrid 改善样例
来源：`acceptance_6_2_modes`
- Query: `What evidence describes method limitations and evaluation outcomes?`
- bm25 top: `35bf14e7f4c2:00063`, `35bf14e7f4c2:00107`, `3226d0151323:00050`, ...
- dense top: `35bf14e7f4c2:00075`, `35bf14e7f4c2:00101`, `1a0a22c1909a:00024`, ...
- hybrid top: `35bf14e7f4c2:00075`, `35bf14e7f4c2:00063`, `3226d0151323:00050`, ...
- 判定：
  - `hybrid_diff_from_bm25 = true`
  - `hybrid_diff_from_dense = true`

## 4) embedding 构建耗时统计
来源：`index_build`
- Round 1:
  - cache_hits: 0
  - cache_miss: 284
  - api_calls: 93
  - failed_items: 12
  - elapsed_sec: 41.084
- Round 2:
  - cache_hits: 272
  - cache_miss: 12
  - api_calls: 12
  - failed_items: 12
  - elapsed_sec: 14.582

## 5) cache 命中率统计
- Round 2 命中率：`272 / 284 = 95.77%`
- 满足“次轮 > 90% hits”目标。

## 6) Dense 20 问可运行验收
来源：`acceptance_6_1_dense20`
- 20/20 均 `retrieval_non_empty = true`
- 20/20 均 `embedding_fields_present = true`

## 结论
- dense 已升级为真实 embedding 检索（cosine），并保留 `dense_backend=tfidf` 回退。
- hybrid 融合与 graph 扩展路径保持兼容。
- embedding 日志字段、缓存统计、运行记录均可复现。
- 本次批量验收在 sample_300 范围内完成，结果详见 `reports/m2_4_eval_summary.json` 与对应 `runs/*`。
