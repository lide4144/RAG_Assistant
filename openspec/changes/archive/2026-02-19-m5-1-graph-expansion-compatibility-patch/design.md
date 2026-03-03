## 上下文

M2.4 将 dense 检索切换为可配置后端（`embedding|tfidf`）后，M5 图扩展仍以“候选分数”作为主要输入，但对候选来源与后端语义的结构化约束不完整。当前问题不在扩展算法本身，而在输入契约与日志可追溯性：难以在 runs 中稳定区分某次扩展来自哪种 retrieval mode、dense backend，以及 embedding 版本上下文。

## 目标 / 非目标

**目标：**
- 统一 graph expansion seeds 的输入元数据契约，确保后端语义可追踪。
- 在扩展产物与运行日志中保留 dense backend 语义，并覆盖关键预算字段。
- 保持 M5 扩展算法逻辑、预算控制与过滤策略不变。

**非目标：**
- 不改写图扩展召回策略、阈值、打分衰减与过滤规则。
- 不新增新的检索模式或外部依赖。
- 不变更 QA CLI 参数语义。

## 决策

### 决策 1：将 backend 元数据作为 seed payload 的强约束字段
- 方案：seed 必须携带 `payload.source`、`payload.dense_backend`、`payload.retrieval_mode`；当 `dense_backend=embedding` 时必须包含 `payload.embedding_provider`、`payload.embedding_model`，`payload.embedding_version` 可选。
- 原因：扩展阶段应消费“已定型”的检索上下文，避免隐式推断。
- 备选：在 graph expansion 内部根据全局配置回填 backend。该方式在混合实验与历史回放下不可靠。

### 决策 2：扩展候选继承 seed backend 语义
- 方案：graph expansion 新增 chunk 的 payload 继承触发该候选的 seed backend 元数据，不允许改写 `dense_backend`。
- 原因：保证扩展后候选链路与初检链路一致，支持端到端归因。
- 备选：扩展候选统一标注为 `graph_expand` 且不携带 backend；该方式会丢失上游语义。

### 决策 3：运行日志最小强制字段
- 方案：runs 必须记录 `dense_backend`、`graph_expand_alpha`、`expansion_added_chunks`、`expansion_budget`。
- 原因：这四项是“后端选择 + 扩展规模控制”最小可复现闭环。
- 备选：仅记录扩展数量，不记录预算和 backend；无法解释候选规模变化原因。

## 风险 / 权衡

- [不同 seed 来源元数据不完整导致扩展拒绝] → 在检索阶段统一补全 payload，并在日志增加缺失计数告警。
- [同一新增 chunk 由不同 backend seed 命中] → 采用“首次命中保留 + 来源计数累计”策略，并在统计中暴露来源分布。
- [日志字段增加导致旧脚本解析失败] → 保持新增字段为追加，不删除旧字段；在校验逻辑中兼容缺省值。

## 迁移计划

1. 在检索候选构建路径补齐 seed payload 标准字段。
2. 在 graph expansion 合并阶段实现 backend 语义继承与约束校验。
3. 在 run trace / qa report 写入新增追踪字段。
4. 增加双后端（tfidf/embedding）回归测试，确认仅候选不同、逻辑一致。
5. 更新评估脚本，验证规模上限：`<= top_k*(1+alpha)` 且 `<= graph_expand_max_candidates`。

## Open Questions

- 当同一 chunk 被不同 backend 的多个 seed 扩展命中时，是否需要在最终 evidence 层保留多来源 backend 列表。
- `embedding_version` 是否应纳入缓存键规范（本次先作为可选追踪字段）。
