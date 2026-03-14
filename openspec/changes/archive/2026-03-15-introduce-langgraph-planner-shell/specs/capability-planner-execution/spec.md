## ADDED Requirements

### 需求:系统必须提供基于 LangGraph 的顶层 planner shell
系统必须在 Python kernel 聊天入口前提供一个基于 LangGraph 的顶层 planner shell，由该 shell 统一承接聊天请求状态、节点调度、失败回退与执行路径选择；禁止将顶层编排继续仅以 `qa.py` 内部隐式分支的方式扩张。

#### 场景:聊天请求先进入 planner shell
- **当** Gateway 转发一条新的聊天请求到 Python kernel
- **那么** 系统必须先进入 LangGraph planner shell，再由 shell 决定后续执行 `catalog`、`summary`、`fact_qa`、`control` 或 legacy fallback 路径

### 需求:系统必须优先稳定主聊天问答路径，其他路径允许兼容接入
第一阶段系统必须优先保证 `Local` 主聊天问答路径可以稳定通过 planner shell 承接；对于 `catalog`、`summary`、`control` 等 Local 内部分支，允许先通过兼容节点、委托现有函数或 passthrough 方式接入；`Web` 与 `Hybrid` 禁止被要求在第一阶段一并迁入 planner shell。

#### 场景:非主路径先以兼容节点接入
- **当** planner shell 路由到 `catalog`、`summary` 或 `control` 路径
- **那么** 系统可以先通过兼容节点或 passthrough 调用现有能力实现，只要 shell 入口、状态对象与回退语义保持统一

#### 场景:Web 与 Hybrid 在第一阶段保持原链路
- **当** 用户以 `web` 或 `hybrid` 模式发起聊天请求
- **那么** 系统必须继续走现有链路，不要求在第一阶段进入 planner shell

### 需求:系统必须为 planner shell 暴露统一状态对象
系统必须为 planner shell 暴露统一状态对象，至少包含请求元信息、planner 决策字段、执行结果字段与响应字段；后续节点必须通过该状态对象读写，不得依赖未声明的临时全局变量或隐式上下文。

#### 场景:节点通过统一状态传递决策与产物
- **当** `plan_chat_request` 节点完成规划
- **那么** 后续路由和执行节点必须从统一状态对象读取 `primary_capability`、`strictness`、`action_plan` 与 `short_circuit` 等字段

### 需求:系统必须保留确定性回退到现有 QA 主路径
当 LangGraph shell 运行失败、状态校验失败、planner 节点不可用或未匹配到受支持路径时，系统必须回退到现有确定性 QA 主路径，并保持聊天链路可继续返回回答；禁止因 shell 故障直接让请求中断。

#### 场景:planner shell 异常时回退 legacy QA
- **当** planner shell 在规划或路由阶段抛出异常
- **那么** 系统必须切换到 legacy QA 路径完成本轮请求，并在观测字段中记录发生了 fallback

## MODIFIED Requirements

### 需求:系统必须提供 planner 与执行器观测字段
系统必须在运行 trace 中输出 planner shell 与执行链路观测字段，至少包含 `planner_used`、`planner_source`、`planner_confidence`、`primary_capability`、`strictness`、`action_plan`、`execution_trace`、`short_circuit`、`truncated` 与 `selected_path`；当触发 shell 回退时还必须记录 `planner_fallback` 与回退原因。

#### 场景:LangGraph shell 链路可审计
- **当** 系统经由 planner shell 完成一次单步或多步请求
- **那么** run trace 必须包含 planner 决策、graph 选择路径、执行轨迹与回退状态，且字段可序列化
