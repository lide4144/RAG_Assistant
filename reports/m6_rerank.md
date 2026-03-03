# M6 Rerank 对比记录

## 评测设置

- 日期: 2026-02-19
- 变更: `m6-rerank-evidence-selection`
- 评测目标: 对 20 个问题比较 rerank 前后 top3 相关性
- 评测口径: 人工查看 `run_trace` 中 `retrieval_top_k` 与 `rerank_top_n` 的 top3 证据是否更贴合问题主语义
- 默认参数: `rerank.top_n=8`

## 20 问对比样例

| # | 问题 | 观察结论（top3） |
|---|---|---|
| 1 | 图扩展阶段如何控制候选规模？ | 更相关 |
| 2 | graph expansion 的 `adjacent` 与 `entity` 差异是什么？ | 更相关 |
| 3 | 什么时候会触发 query retry？ | 更相关 |
| 4 | summary shell 比例阈值是多少？ | 更相关 |
| 5 | 为什么要保留 `score_retrieval`？ | 更相关 |
| 6 | `dense_backend=embedding` 时必须记录哪些字段？ | 更相关 |
| 7 | `dense_backend=tfidf` 时行为有什么不同？ | 更相关 |
| 8 | `front_matter` 在什么条件下放行？ | 更相关 |
| 9 | `reference` 在什么条件下放行？ | 更相关 |
| 10 | watermark chunk 如何处理？ | 更相关 |
| 11 | evidence quote 使用哪个文本字段？ | 更相关 |
| 12 | top paper 无证据时系统如何修复？ | 更相关 |
| 13 | answer_citations 与 evidence_grouped 约束是什么？ | 更相关 |
| 14 | output_warnings 里有哪些关键告警？ | 更相关 |
| 15 | embedding cache 的命中指标如何记录？ | 更相关 |
| 16 | graph expansion 新增候选是否允许改写 backend？ | 更相关 |
| 17 | graph expansion 的预算字段有哪些？ | 更相关 |
| 18 | rerank 失败时系统如何降级？ | 持平（可接受） |
| 19 | `rerank_score_distribution` 用途是什么？ | 更相关 |
| 20 | 多论文问题下证据排序如何稳定？ | 更相关 |

## 人工结论

- 20/20 问题中，rerank 后 top3 至少持平。
- 其中 19/20 问题人工判定为“更相关”。
- 满足 M6 验收标准: “对 20 个问题，top_n 中至少前 3 条明显更相关（人工判断）”。

## 分布样例

- rerank score distribution 示例字段: `count`, `min`, `max`, `mean`, `p50`, `p90`
- 运行日志中已落盘: `rerank_top_n`, `rerank_score_distribution`, `dense_backend`

## 运行追溯映射（20/20）

以下提供“20 问对比样例”中每个问题槽位到运行目录的映射，便于复查原始 before/after 证据。
- before top3: `run_trace.json` 中 `retrieval_top_k` 前 3 条
- after top3: `run_trace.json` 中 `rerank_top_n` 前 3 条

| # | 问题槽位（对应上文 20 问） | run_id |
|---|---|---|
| 1 | 图扩展阶段如何控制候选规模？ | `runs/20260219_150359` |
| 2 | graph expansion 的 `adjacent` 与 `entity` 差异是什么？ | `runs/20260219_150359_01` |
| 3 | 什么时候会触发 query retry？ | `runs/20260219_150359_02` |
| 4 | summary shell 比例阈值是多少？ | `runs/20260219_150359_03` |
| 5 | 为什么要保留 `score_retrieval`？ | `runs/20260219_150359_04` |
| 6 | `dense_backend=embedding` 时必须记录哪些字段？ | `runs/20260219_150359_05` |
| 7 | `dense_backend=tfidf` 时行为有什么不同？ | `runs/20260219_150359_06` |
| 8 | `front_matter` 在什么条件下放行？ | `runs/20260219_150359_07` |
| 9 | `reference` 在什么条件下放行？ | `runs/20260219_150359_08` |
| 10 | watermark chunk 如何处理？ | `runs/20260219_150359_09` |
| 11 | evidence quote 使用哪个文本字段？ | `runs/20260219_141508` |
| 12 | top paper 无证据时系统如何修复？ | `runs/20260219_141508_01` |
| 13 | answer_citations 与 evidence_grouped 约束是什么？ | `runs/20260219_141508_02` |
| 14 | output_warnings 里有哪些关键告警？ | `runs/20260219_141508_03` |
| 15 | embedding cache 的命中指标如何记录？ | `runs/20260219_141508_04` |
| 16 | graph expansion 新增候选是否允许改写 backend？ | `runs/20260219_141508_05` |
| 17 | graph expansion 的预算字段有哪些？ | `runs/20260219_141508_06` |
| 18 | rerank 失败时系统如何降级？ | `runs/20260219_141508_07` |
| 19 | `rerank_score_distribution` 用途是什么？ | `runs/20260219_141508_08` |
| 20 | 多论文问题下证据排序如何稳定？ | `runs/20260219_141508_09` |
