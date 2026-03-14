## ADDED Requirements

### 需求:系统必须将聊天请求优先路由到 planner shell 入口
Node Gateway 在处理聊天请求时必须优先将 `Local` 模式请求转发到 Python kernel 的 planner shell 独立入口，并由该入口统一决定后续能力路径；禁止 Gateway 自行复制 planner/skill 路由规则。

#### 场景:Gateway 使用 planner shell 作为聊天入口
- **当** 前端以 `Local` 模式通过 WebSocket 发送 `chat` 事件
- **那么** Gateway 必须将该请求发送到 Python kernel 的 `/planner/qa` 或 `/planner/qa/stream`，而不是直接在 Gateway 内判断走哪条能力链路

#### 场景:Web 与 Hybrid 保持现有入口
- **当** 前端以 `Web` 或 `Hybrid` 模式发送 `chat` 事件
- **那么** Gateway 必须继续使用现有链路，而不是在第一阶段强制切到 planner shell

### 需求:系统必须保持 Gateway 对前端的统一事件协议不变
即使 Gateway 改为调用 planner shell 入口，Gateway 对前端输出的聊天事件协议也必须保持兼容，至少继续提供 `message`、`sources`、`messageEnd` 与 `error` 事件，禁止因 planner shell 引入新的后端层而破坏既有前端消费契约。

#### 场景:切换 planner shell 后前端仍消费标准事件
- **当** planner shell 返回流式回答与来源信息
- **那么** Gateway 必须继续以现有标准事件结构向前端发送消息，而不是暴露 LangGraph 内部节点事件

## MODIFIED Requirements

### 需求:系统必须提供网关统一编排入口
系统必须提供 Node Gateway 作为前端统一入口，Gateway 必须负责把 `Local` 聊天请求转发到 Python kernel 的 planner shell 独立灰度入口或兼容回退入口，并向前端屏蔽后端异构实现细节；Gateway 可以决定协议层入口和回退策略，但禁止承担 planner 能力选择或具体 Skill 编排职责。

#### 场景:Gateway 在 planner shell 与回退入口之间切换
- **当** Python kernel 的 planner shell 暂时不可用或被配置关闭
- **那么** Gateway 必须能够回退到兼容聊天入口，同时保持对前端仍是同一个统一网关入口
