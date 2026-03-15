## 新增需求

### 需求:系统必须让 Gateway 以语义透明方式转发 agent 执行事件
Gateway 在转发 agent 执行事件时必须保持语义透明：它必须知道如何接收、归一化并转发受支持的高层执行事件，但禁止在 Node 侧复制 planner 决策、tool registry、执行编排或跨请求 agent 状态管理；所有 agent-first 执行语义真相源必须继续留在 Python kernel runtime。

#### 场景:新增 tool 不要求 Gateway 增加专有执行逻辑
- **当** planner runtime 后续新增一个已注册工具，并通过稳定高层事件报告其执行状态
- **那么** Gateway 必须仍然只依赖通用事件类型和稳定摘要字段工作，而不需要为该工具新增专有路由规则或状态机

#### 场景:Gateway 不得根据事件自行改写执行路径
- **当** Gateway 收到来自 Python kernel 的 `planning`、`toolRunning` 或 `fallback` 事件
- **那么** Gateway 必须仅做协议归一化和转发，而不得基于这些事件自行推导新的 planner 决策或切换新的工具执行路径

## 修改需求

### 需求:系统必须提供统一 WebSocket 事件协议
网关必须输出统一事件协议，至少包含 `message`、`sources`、`messageEnd`、`error` 四类基础聊天事件，并支持 agent-first 高层执行事件与任务型事件并行共存；在 agent-first 架构下，Gateway 可以向前端转发 `planning`、`toolSelection`、`toolRunning`、`toolResult`、`fallback` 等稳定高层执行事件，但禁止直接暴露 planner runtime 内部节点、tool 私有实现细节或非稳定执行 trace 给当前前端协议层，除非后续专门变更重新定义协议。

#### 场景:planner runtime 升级后前端仍消费标准聊天事件
- **当** planner runtime 在内部完成规划、tool 调用和受控回退
- **那么** Gateway 必须仍然以现有标准聊天事件结构完成回答输出，而不是要求前端改用内部 runtime 协议才能拿到最终回答

#### 场景:统一流中并存 agent 事件与任务事件
- **当** 前端同时消费聊天回答、高层 agent 执行状态与后台任务进度
- **那么** Gateway 必须保证这些事件仍可按 `traceId/taskId` 分域消费，且 agent 执行事件不会污染任务进度语义，任务事件也不会伪装成 agent 事件

#### 场景:受控降级不等同于错误终态
- **当** planner runtime 触发受支持的兼容回退或 tool 级降级，但本轮请求仍可继续返回回答
- **那么** Gateway 必须转发高层 `fallback` 语义并继续保持标准聊天事件闭合，而不是把该降级直接映射为 `error`

## 移除需求
