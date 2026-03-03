## ADDED Requirements

### 需求:扩展候选缺失 embedding 分数时必须继承 seed 分数
在 embedding dense 或 hybrid 检索路径中，扩展候选若没有直接 dense 分数，系统必须继承对应 seed chunk 分数并施加衰减系数：`adjacent=0.97`、`entity=0.94`。系统禁止为扩展候选重新调用 embedding API。

#### 场景:扩展候选分数继承
- **当** 扩展得到的新候选未在初检 dense 结果中出现
- **那么** 系统必须按边类型继承 seed 分数并应用衰减，且不得触发新的 embedding 请求

## MODIFIED Requirements

### 需求:系统必须执行 1-hop 图扩展召回
系统必须对初检 `top_k` 的每个 seed chunk 调用图邻居查询，并同时覆盖 `adjacent` 与 `entity` 两类 1-hop 邻居，形成扩展候选集合。无论初检 dense backend 为 embedding 还是 TF-IDF，系统都必须在初检后执行图扩展。

#### 场景:对每个 seed 执行双类型扩展
- **当** 初检返回 `top_k` 候选且图数据可用
- **那么** 系统必须对每个 seed chunk 至少尝试一次 `neighbors(type=adjacent, hop=1)` 与 `neighbors(type=entity, hop=1)`
