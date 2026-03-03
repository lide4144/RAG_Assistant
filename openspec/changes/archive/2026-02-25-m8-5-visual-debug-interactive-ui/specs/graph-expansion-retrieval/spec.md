## MODIFIED Requirements

### 需求:系统必须对扩展候选按 chunk_id 去重并保留来源统计
系统必须以 `chunk_id` 去重合并 seed 与扩展候选，并记录扩展统计（如新增数量、过滤数量、来源类型分布）以支持验收。系统必须在候选 payload 中记录来源与后端语义：`source`、`retrieval_mode`、`dense_backend`。当新增候选由 graph expansion 产生时，系统必须保留 `source=graph_expand`，并继承触发 seed 的 `retrieval_mode` 与 `dense_backend`。系统必须将该 `source` 信息透传到最终 `evidence_grouped`，以支持 UI 审查层区分 BM25、Dense、Graph Expand 来源。

#### 场景:存在重复邻居
- **当** 同一 chunk 同时由多个 seed 或多种边类型扩展命中
- **那么** 系统必须仅保留一条候选记录，并在统计信息中保留来源计数

#### 场景:扩展候选语义继承
- **当** graph expansion 新增候选来自某个 seed
- **那么** 新增候选必须继承该 seed 的 `dense_backend` 与 `retrieval_mode`，且禁止在扩展阶段改写 backend 语义

#### 场景:来源透传到审查面板
- **当** graph expansion 候选进入最终 evidence 输出
- **那么** evidence 条目必须保留 `source=graph_expand` 并可在 UI 审查中直接区分显示
