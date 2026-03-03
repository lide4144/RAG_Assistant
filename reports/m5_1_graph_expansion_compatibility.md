# M5.1 Graph Expansion Compatibility Patch 验收记录

## 目标

在不改变 M5 图扩展算法逻辑的前提下，补齐 seeds 输入契约与 runs 日志追踪字段，支持 `dense_backend=tfidf|embedding` 的可复现对比。

## 本次变更要点

- seeds payload 补齐：`source`、`dense_backend`、`retrieval_mode`
- `dense_backend=embedding` 时透传：`embedding_provider`、`embedding_model`（可选 `embedding_version`）
- graph expansion 新增候选继承 seed 的 backend 语义，不改写 `dense_backend`
- runs 新增/强化追踪：`dense_backend`、`graph_expand_alpha`、`expansion_added_chunks`、`expansion_budget`

## 验收结论

- [x] `dense_backend=tfidf` 与 `dense_backend=embedding` 均可进入 graph expansion
- [x] 扩展候选保持 `source=graph_expand`，并继承 seed backend 元数据
- [x] run_trace/qa_report 可区分 backend，并记录扩展预算字段
- [x] 候选规模约束仍满足：`<= top_k*(1+alpha)` 且 `<= graph_expand_max_candidates`

## 关联测试

- `tests/test_m5_graph_expansion.py`
- `tests/test_m2_retrieval_qa.py`
- `tests/test_runlog_and_config.py`
