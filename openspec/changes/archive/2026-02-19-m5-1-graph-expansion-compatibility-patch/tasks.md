## 1. Seeds 输入契约补齐

- [x] 1.1 在检索候选构建路径统一补齐 `payload.source`、`payload.dense_backend`、`payload.retrieval_mode`
- [x] 1.2 在 `dense_backend=embedding` 时补齐 `payload.embedding_provider`、`payload.embedding_model`，并支持可选 `payload.embedding_version`
- [x] 1.3 为 seeds 输出新增字段增加序列化与空值兼容处理，避免现有调用方中断

## 2. Graph Expansion 兼容语义继承

- [x] 2.1 在 graph expansion 新增候选逻辑中继承触发 seed 的 `dense_backend` 与 `retrieval_mode`
- [x] 2.2 保持扩展候选 `source=graph_expand`，并合并来源计数而不改写 backend 语义
- [x] 2.3 在 embedding 路径下透传 `embedding_provider`、`embedding_model`（可选 `embedding_version`）到扩展候选 payload

## 3. 运行日志与追踪字段增强

- [x] 3.1 在 run trace/qa report 中新增并落盘 `dense_backend`
- [x] 3.2 在 graph expansion 统计中落盘 `graph_expand_alpha`、`expansion_added_chunks`、`expansion_budget`
- [x] 3.3 更新日志校验逻辑，保证新增字段可序列化且与历史字段兼容

## 4. 约束验证与回归测试

- [x] 4.1 增加 `dense_backend=tfidf` 与 `dense_backend=embedding` 两条回归用例，验证扩展逻辑一致且仅候选差异
- [x] 4.2 增加扩展规模约束测试：`<= top_k*(1+alpha)` 且 `<= graph_expand_max_candidates`
- [x] 4.3 增加 payload 继承与完整性测试：新增候选必须继承 backend 语义，embedding 模式下必须携带 provider/model

## 5. 验收与文档同步

- [x] 5.1 生成/更新 M5.1 验收记录，覆盖双后端日志可追溯性与候选规模约束
- [x] 5.2 更新 README 或评估说明中的运行日志字段说明，标注 M5.1 兼容补丁字段
