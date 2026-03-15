## MODIFIED Requirements

### 需求:系统必须提供网关统一编排入口
系统必须提供 Node Gateway 作为前端统一入口；在 agent-first 架构下，Gateway 必须负责把 `Local` 聊天请求转发到 Python kernel 的 planner runtime 入口或兼容回退入口，把 `Web` 请求路由到现有 web 链路，并向前端屏蔽后端异构实现细节；Gateway 可以决定协议层入口与兼容回退策略，但禁止承担 planner 决策、tool 选择或 agent 执行语义解释职责。

#### 场景:Gateway 将 planner runtime 视为 Local 唯一顶层后端
- **当** 前端以 `Local` 模式通过 WebSocket 发送 `chat` 事件
- **那么** Gateway 必须把请求发送到 Python kernel 的 planner runtime 入口，而不是在 Gateway 内复制 planner 能力选择逻辑

#### 场景:Gateway 在 runtime 不可用时做兼容回退
- **当** Python kernel 的 planner runtime 暂时不可用、关闭或返回受支持的降级状态
- **那么** Gateway 必须能够回退到兼容聊天入口，同时保持对前端仍是同一个统一网关入口

### 需求:系统必须提供统一 WebSocket 事件协议
网关必须输出统一事件协议，至少包含 `message`、`sources`、`messageEnd`、`error` 四类聊天事件，并支持任务型事件与聊天事件并行共存；在 agent-first 架构下，Gateway 禁止直接暴露 planner runtime 内部节点、tool 细节或非稳定执行事件给当前前端协议层，除非后续专门变更重新定义协议。

#### 场景:planner runtime 升级后前端仍消费标准事件
- **当** planner runtime 在内部完成规划、tool 调用和回退
- **那么** Gateway 必须仍然以现有标准事件结构向前端发送消息，而不是将内部 agent 事件直接透出到当前聊天协议

## ADDED Requirements

### 需求:系统必须保持 Gateway 对 planner runtime 的语义透明
Gateway 对 planner runtime 必须保持语义透明：它必须知道“把流量发往哪里”和“何时执行兼容回退”，但禁止在 Node 侧引入与 Python runtime 重复的 capability taxonomy、tool registry 或策略判断；所有 agent-first 语义真相源必须留在 Python kernel。

#### 场景:新增 tool 不需要 Gateway 同步理解其语义
- **当** 后续变更向 planner runtime 新增一个可调用 tool
- **那么** Gateway 必须仍只依赖稳定入口和响应契约工作，而不需要同步新增该 tool 的专有路由规则
