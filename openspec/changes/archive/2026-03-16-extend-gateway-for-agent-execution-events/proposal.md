## 为什么

当前 agent-first 路线已经把顶层 planner/runtime 真相源收敛到 Python kernel，但 gateway 对前端仍主要输出 `message`、`sources`、`messageEnd`、`error` 这类回答型事件，缺少能够表达“正在规划、已选工具、工具执行中、结果已返回、已触发降级”等高层执行状态的稳定协议。随着 planner runtime 逐步替代旧的薄路由壳层，如果不先定义这层高层事件语义，前端将无法在统一入口下感知 agent-first 执行进展，Gateway 与 kernel 之间也容易临时扩张出不稳定的私有事件。

现在需要在不把 Gateway 做成重状态 agent runtime 的前提下，扩展统一事件协议，补上 planner 高层执行状态与兼容回退语义，同时继续保持现有聊天事件和前端接入方式可兼容。

## 变更内容

- 为 Gateway 增加一组面向 agent-first planner runtime 的高层执行事件语义，覆盖 `planning`、`tool_selection`、`tool_running`、`tool_result`、`degraded/fallback` 等阶段。
- 规定这些新增事件属于高层执行状态，而非内部 trace 透传；禁止暴露 LangGraph 节点细节、底层函数名或过细执行栈。
- 保持前端统一入口与既有聊天事件兼容，确保 `message`、`sources`、`messageEnd`、`error` 仍然是稳定基础事件，新增 agent 事件仅作为可选增强并与其并存。
- 明确 Gateway 只负责协议转发、归一化和兼容降级，不承担 planner 决策、tool 选择或长期会话状态管理。
- 约束降级事件的语义，使前端能够区分“planner/runtime 继续工作但走了受控回退”与“请求整体失败”。

## 功能 (Capabilities)

### 新增功能

- `gateway-agent-execution-events`: 定义 Gateway 面向 agent-first planner runtime 输出的高层执行事件类型、最小字段、事件顺序与降级语义。

### 修改功能

- `node-gateway-orchestration`: 网关统一协议需要扩展为可承载 agent-first 高层执行状态，同时继续保持语义透明、统一入口和兼容回退职责边界。

## 影响

- `gateway` 的 WebSocket 事件协议、事件归一化逻辑与 Python kernel adapter。
- Python kernel planner/runtime 对 Gateway 暴露的高层执行事件 envelope。
- 前端聊天入口的事件消费契约与兼容策略，但不包含具体展示设计。
- 与聊天流、错误流、兼容回退和 agent 执行观测相关的协议测试。
