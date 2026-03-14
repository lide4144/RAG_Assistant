# node-gateway-orchestration 规范

## 目的
定义 Node Gateway 作为前端统一入口时的聊天、任务与协议编排边界，确保前端可通过单一网关接入 kernel、web 能力以及阶段性引入的 planner shell。
## 需求
### 需求:系统必须提供网关统一编排入口
系统必须提供 Node Gateway 作为前端统一入口；第一阶段中，Gateway 必须负责把 `Local` 聊天请求转发到 Python kernel 的 planner shell 独立灰度入口或兼容回退入口，把 `Web` 请求路由到现有 web 链路，并向前端屏蔽后端异构实现细节；Gateway 可以决定协议层入口和回退策略，但禁止承担 planner 能力选择或具体 Skill 编排职责。

#### 场景:同一前端入口路由不同后端
- **当** 用户分别以 `Local` 与 `Web` 模式发起问题
- **那么** 网关必须将请求路由到对应后端能力，并返回统一结构响应

#### 场景:Gateway 使用 planner shell 作为 Local 聊天入口
- **当** 前端以 `Local` 模式通过 WebSocket 发送 `chat` 事件
- **那么** Gateway 必须将该请求发送到 Python kernel 的 `/planner/qa` 或 `/planner/qa/stream`，而不是直接在 Gateway 内判断走哪条能力链路

#### 场景:Web 与 Hybrid 保持现有入口
- **当** 前端以 `Web` 或 `Hybrid` 模式发送 `chat` 事件
- **那么** Gateway 必须继续使用现有链路，而不是在第一阶段强制切到 planner shell

#### 场景:Gateway 在 planner shell 与回退入口之间切换
- **当** Python kernel 的 planner shell 暂时不可用或被配置关闭
- **那么** Gateway 必须能够回退到兼容聊天入口，同时保持对前端仍是同一个统一网关入口

### 需求:系统必须提供统一 WebSocket 事件协议
网关必须输出统一事件协议，至少包含 `message`、`sources`、`messageEnd`、`error` 四类聊天事件，并支持任务型事件（如任务状态与进度）与聊天事件并行共存；禁止不同后端返回不兼容事件结构。

#### 场景:后端异常时输出标准错误事件
- **当** 任一后端处理失败
- **那么** 网关必须输出 `error` 事件并附带可追踪错误码，且连接可继续处理下一轮请求

#### 场景:任务与聊天事件并行
- **当** 前端同时存在聊天请求与后台图构建任务
- **那么** 网关必须保证事件可按 `traceId/taskId` 分域消费，且两类事件互不污染

#### 场景:切换 planner shell 后前端仍消费标准事件
- **当** planner shell 返回流式回答与来源信息
- **那么** Gateway 必须继续以现有标准事件结构向前端发送消息，而不是暴露 LangGraph 内部节点事件

### 需求:系统必须提供任务进度事件编排能力
网关必须支持转发非聊天任务的结构化进度事件，至少覆盖任务启动、进度更新、结束结果与错误事件，禁止仅编排聊天回答事件。

#### 场景:转发图构建进度
- **当** 内核上报图构建任务进度
- **那么** 网关必须将其转换并转发为统一任务事件给前端
