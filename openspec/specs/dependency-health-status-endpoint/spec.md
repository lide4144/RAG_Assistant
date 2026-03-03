# dependency-health-status-endpoint 规范

## 目的
待定 - 由归档变更 unify-embedding-rerank-dynamic-routing 创建。归档后请更新目的。
## 需求
### 需求:系统必须提供 /health/deps 三路依赖状态
系统必须提供 `/health/deps` 接口并返回 answer、embedding、rerank 三路状态。每一路状态必须至少包含 `status`、`provider`、`model`、`checked_at` 与 `reason`（失败时）。

#### 场景:健康接口返回三路状态
- **当** 运维调用 `/health/deps`
- **那么** 响应必须同时包含 answer、embedding、rerank 三个独立状态对象

### 需求:健康状态必须暴露降级相关诊断
当 embedding 路径因维度不一致被阻断时，健康状态必须明确标记 `dimension_mismatch` 并指示词频降级；当 rerank 进入静默穿透时，健康状态必须暴露 `passthrough_mode=true` 与最近失败原因。

#### 场景:embedding 维度不一致被标记
- **当** embedding 主备模型或查询向量与索引维度不一致
- **那么** `/health/deps` 必须返回 `embedding.status=degraded` 且 `reason` 包含 `dimension_mismatch`

