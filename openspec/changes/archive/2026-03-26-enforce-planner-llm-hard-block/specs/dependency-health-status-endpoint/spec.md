## 新增需求

### 需求:系统必须在健康检查中暴露 planner LLM 服务阻断状态
系统必须在 `/health/deps` 或等价依赖健康接口中显式暴露 planner LLM 基础设施的可服务状态。该状态必须至少说明 planner 配置是否完整、当前是否处于服务阻断、阻断原因代码，以及该阻断是否影响正式聊天入口可用性；禁止仅通过普通 answer/embedding/rerank 依赖状态暗示 planner 是否可用。

#### 场景:planner 基础设施缺失被健康检查标记为阻断
- **当** planner model 缺失、planner API key 缺失或正式模式配置被判定为无效
- **那么** 健康检查必须显式返回 planner 相关阻断状态和稳定 reason code，并表明正式聊天不可服务

