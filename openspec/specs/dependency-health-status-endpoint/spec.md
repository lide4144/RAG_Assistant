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

### 需求:系统必须在健康检查中暴露 planner LLM 服务阻断状态
系统必须在 `/health/deps` 或等价依赖健康接口中显式暴露 planner LLM 基础设施的可服务状态。该状态必须至少说明 planner 配置是否完整、当前是否处于服务阻断、阻断原因代码，以及该阻断是否影响正式聊天入口可用性；禁止仅通过普通 answer/embedding/rerank 依赖状态暗示 planner 是否可用。

#### 场景:planner 基础设施缺失被健康检查标记为阻断
- **当** planner model 缺失、planner API key 缺失或正式模式配置被判定为无效
- **那么** 健康检查必须显式返回 planner 相关阻断状态和稳定 reason code，并表明正式聊天不可服务

