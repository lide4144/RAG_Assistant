# graph-expansion-retrieval 规范

## 目的
待定 - 由归档变更 m5-graph-expansion-retrieval 创建。归档后请更新目的。
## 需求
### 需求:系统必须执行 1-hop 图扩展召回
系统必须对初检 `top_k` 的每个 seed chunk 调用图邻居查询，并同时覆盖 `adjacent` 与 `entity` 两类 1-hop 邻居，形成扩展候选集合。无论初检 dense backend 为 embedding 还是 TF-IDF，系统都必须在初检后执行图扩展。

#### 场景:对每个 seed 执行双类型扩展
- **当** 初检返回 `top_k` 候选且图数据可用
- **那么** 系统必须对每个 seed chunk 至少尝试一次 `neighbors(type=adjacent, hop=1)` 与 `neighbors(type=entity, hop=1)`

### 需求:系统必须按内容类型与查询意图过滤扩展候选
系统必须在扩展候选入池前执行强约束过滤：`watermark` 必须直接剔除；`front_matter` 必须默认剔除，仅当 query 命中作者/机构相关词时放行；`reference` 必须默认不扩展，仅当 query 命中“引用/出处/验证/量表”相关词时放行。

#### 场景:默认过滤噪声类型
- **当** 扩展命中 `watermark`、`front_matter`、`reference` 候选且 query 未命中对应意图词
- **那么** 系统必须剔除这些候选，且不得计入可用扩展集合

#### 场景:意图命中时放行特定类型
- **当** query 命中作者/机构或引用验证类意图词
- **那么** 系统必须仅放行与命中意图对应的 `front_matter` 或 `reference` 候选

### 需求:系统必须控制扩展后候选规模
系统必须保证扩展后总候选数满足 `total_candidates <= top_k * (1 + alpha)`，并在去重后满足全局上限 `<= 200`。

#### 场景:扩展预算触顶
- **当** 可扩展邻居数量超过预算
- **那么** 系统必须截断扩展候选，使最终候选总量不超过比例上限与全局上限

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

### 需求:扩展候选缺失 embedding 分数时必须继承 seed 分数
在 embedding dense 或 hybrid 检索路径中，扩展候选若没有直接 dense 分数，系统必须继承对应 seed chunk 分数并施加衰减系数：`adjacent=0.97`、`entity=0.94`。系统禁止为扩展候选重新调用 embedding API。该继承过程必须保持 seed 的 `dense_backend=embedding` 语义并透传 embedding 元数据（`embedding_provider`、`embedding_model`，可选 `embedding_version`）。

#### 场景:扩展候选分数继承
- **当** 扩展得到的新候选未在初检 dense 结果中出现
- **那么** 系统必须按边类型继承 seed 分数并应用衰减，且不得触发新的 embedding 请求

#### 场景:embedding 元数据透传
- **当** `dense_backend=embedding` 的 seed 触发新增候选
- **那么** 新增候选 payload 必须包含 `embedding_provider` 与 `embedding_model`，并允许包含可选的 `embedding_version`

