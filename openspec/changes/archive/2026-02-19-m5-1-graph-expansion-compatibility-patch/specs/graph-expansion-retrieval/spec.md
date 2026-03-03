## 新增需求

## 修改需求

### 需求:系统必须对扩展候选按 chunk_id 去重并保留来源统计
系统必须以 `chunk_id` 去重合并 seed 与扩展候选，并记录扩展统计（如新增数量、过滤数量、来源类型分布）以支持验收。系统必须在候选 payload 中记录来源与后端语义：`source`、`retrieval_mode`、`dense_backend`。当新增候选由 graph expansion 产生时，系统必须保留 `source=graph_expand`，并继承触发 seed 的 `retrieval_mode` 与 `dense_backend`。

#### 场景:存在重复邻居
- **当** 同一 chunk 同时由多个 seed 或多种边类型扩展命中
- **那么** 系统必须仅保留一条候选记录，并在统计信息中保留来源计数

#### 场景:扩展候选语义继承
- **当** graph expansion 新增候选来自某个 seed
- **那么** 新增候选必须继承该 seed 的 `dense_backend` 与 `retrieval_mode`，且禁止在扩展阶段改写 backend 语义

### 需求:扩展候选缺失 embedding 分数时必须继承 seed 分数
在 embedding dense 或 hybrid 检索路径中，扩展候选若没有直接 dense 分数，系统必须继承对应 seed chunk 分数并施加衰减系数：`adjacent=0.97`、`entity=0.94`。系统禁止为扩展候选重新调用 embedding API。该继承过程必须保持 seed 的 `dense_backend=embedding` 语义并透传 embedding 元数据（`embedding_provider`、`embedding_model`，可选 `embedding_version`）。

#### 场景:扩展候选分数继承
- **当** 扩展得到的新候选未在初检 dense 结果中出现
- **那么** 系统必须按边类型继承 seed 分数并应用衰减，且不得触发新的 embedding 请求

#### 场景:embedding 元数据透传
- **当** `dense_backend=embedding` 的 seed 触发新增候选
- **那么** 新增候选 payload 必须包含 `embedding_provider` 与 `embedding_model`，并允许包含可选的 `embedding_version`

## 移除需求
