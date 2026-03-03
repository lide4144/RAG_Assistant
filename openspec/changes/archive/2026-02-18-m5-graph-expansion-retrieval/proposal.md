## 为什么

当前检索流程在初检 top-k 后缺少结构化扩展，导致多跳与对比类问题常出现关键上下文缺失。M4 已具备图查询能力，M5 需要将其接入召回链路，在可控候选规模内补全证据。

## 变更内容

- 新增基于图邻居的 1-hop 扩展召回流程：对每个初检 chunk 执行 `adjacent` 与 `entity` 两类扩展。
- 新增扩展候选过滤规则：
  - `watermark` 直接剔除。
  - `front_matter` 默认剔除，仅在 query 命中作者/机构意图词时纳入。
  - `reference` 默认不扩展，仅在 query 命中“引用/出处/验证/量表”等意图词时纳入。
- 新增扩展规模控制：扩展后候选总量满足 `expanded <= top_k * (1 + alpha)`，并在去重后设置全局上限（默认不超过 200）。
- 将扩展候选并入后续排序与证据分配输入，保证与既有 QA 输出结构兼容。

## 功能 (Capabilities)

### 新增功能
- `graph-expansion-retrieval`: 基于 `graph.neighbors` 在初检结果上进行图扩展召回，提供过滤与规模控制，提升多跳问题的上下文覆盖。

### 修改功能
- `rag-baseline-retrieval`: 初检后召回阶段从“仅初检候选”调整为“初检 + 图扩展候选”，并要求记录扩展统计信息。

## 影响

- 代码：`app/retrieval.py`、`app/qa.py`、可能新增 `app/graph_expand.py`（或同等模块）。
- 配置：新增扩展参数（如 `graph_expand_alpha`、`graph_expand_max_candidates`、意图词表）。
- 数据与运行记录：在 `run_trace`/`qa_report` 中新增扩展候选规模与过滤原因统计字段。
- 测试与报告：新增 M5 扩展召回单测与至少 10 个多跳/对比问题的人工验收记录。
