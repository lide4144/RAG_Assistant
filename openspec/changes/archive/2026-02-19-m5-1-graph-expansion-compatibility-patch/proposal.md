## 为什么

M2.4 引入 embedding dense 检索后，M5 Graph Expansion 的 seeds 输入与运行日志缺少对 dense backend 的显式追踪，导致跨实验复现与结果归因困难。需要在不改变 M5 扩展算法逻辑的前提下，补齐输入契约与可观测字段。

## 变更内容

- 为 M5 Graph Expansion 的 seeds 输入增加后端兼容元数据要求：`payload.source`、`payload.dense_backend`、`payload.retrieval_mode`。
- 在 `dense_backend=embedding` 时，要求 seeds 额外携带 `payload.embedding_provider`、`payload.embedding_model`，并支持可选 `payload.embedding_version`。
- 约束 graph expansion 新增候选继承原 seed 的 `dense_backend` 语义，不允许在扩展阶段改写后端语义。
- 增强 runs 日志，确保记录并可回溯：`dense_backend`、`graph_expand_alpha`、`expansion_added_chunks`、`expansion_budget`。
- 保持 M5 扩展策略与打分逻辑不变；仅调整输入结构契约与追踪字段。

## 功能 (Capabilities)

### 新增功能
- 无

### 修改功能
- `graph-expansion-retrieval`: 扩展 seeds 输入契约，要求携带 retrieval 来源与 dense backend 元数据；新增候选继承 backend 语义；补充运行日志追踪字段。
- `rag-baseline-retrieval`: 对接并输出可被 M5 消费的 retrieval 元数据（source/retrieval_mode/dense_backend 及 embedding 模式下的 provider/model/version）。

## 影响

- 受影响代码：`app/retrieve.py`（候选结构与 graph expansion 输入/继承规则）、`app/qa.py`（runs trace/qa report 追踪字段汇总）、可能涉及日志校验与序列化模块（如 `app/runlog.py`）。
- 受影响产物：`runs/<timestamp>/run_trace.json`、`runs/<timestamp>/qa_report.json` 字段更完整。
- 对外 API/CLI：命令行接口不变，属于内部数据契约与可观测性增强。
