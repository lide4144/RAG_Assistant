## 上下文

当前仓库已经在 `app/qa.py` 中接入了前置 planner 契约、`action_plan`、`strictness`、短路控制与 trace 字段，`app/capability_planner.py` 也提供了规则版规划结果。与此同时，Gateway 仍然把聊天流量视为“直接调用 Python kernel `/qa` 或 `/qa/stream`”的单一路径，缺少一个显式的顶层编排入口来承接后续 Planner / Skill 演进。

这导致两个问题：

- Python 侧已经开始出现 planner 语义，但编排边界仍埋在 `qa.py` 内部，不利于扩展新 Skill、替换规划实现或复用统一状态对象。
- Gateway 只知道“把聊天请求发给 kernel QA”，没有明确“请求先进入 planner shell，再由 planner 决定是否走现有 QA / catalog / control / summary 路径”的契约。

本次变更目标不是重写现有 QA 流程，而是为其外面增加一个 LangGraph 顶层壳层，吸收编排职责，同时保持已有 kernel 能力接口和流式输出协议可继续工作。

约束：

- 必须保留现有 `frontend -> gateway -> python kernel` 主链路。
- 不重写底层检索、重排、回答生成、证据门控与会话状态存储。
- Planner 壳层失效时必须能回退到现有确定性 QA 主路径，不能让聊天链路不可用。
- Gateway 对前端暴露的 WebSocket 事件结构不得被破坏。

## 目标 / 非目标

**目标：**

- 在 Python kernel 中提供一个基于 LangGraph 的顶层 planner shell，统一承接聊天请求的入口状态、节点调度和回退。
- 第一阶段先稳定承接现有 `Local` 主聊天问答路径，确保 Local 聊天主链路可在不改变内部能力实现的前提下被 shell 包裹。
- 将现有规则 planner、catalog lookup、summary / fact QA、control 路径封装为 shell 内的受控节点，而不是继续散落在 `qa.py` 的隐式分支里。
- 定义稳定的 planner state、节点命名、执行结果与 trace 映射，便于后续 Skill 继续挂接。
- 明确 Gateway 如何以独立灰度端点方式把 `Local` 聊天请求转发到 planner shell，同时保持现有 `/qa`、`/qa/stream` 兼容和可回滚。

**非目标：**

- 不在本次变更中引入开放式 agent 工具调用或无限步工作流。
- 不替换现有前端页面、WebSocket 事件协议或任务事件协议。
- 不要求第一阶段就用 LLM planner 取代现有规则 planner。
- 不改写底层 kernel 能力函数的业务语义，只整理其被调用方式与入口边界。
- 不要求第一阶段把 catalog、summary、control 等非主聊天问答路径重整到与主路径同等深度，允许先以兼容节点或 passthrough 方式挂接。
- 不要求第一阶段把 `Web`、`Hybrid` 一并迁入 planner shell；这两种 mode 继续沿用现有链路。

## 决策

### 决策 1：把 LangGraph 用作“顶层壳层”，而不是重写整个 Kernel 流程

LangGraph 只负责承载顶层状态流转、节点连接、失败回退与统一入口；具体执行节点仍调用现有 kernel 逻辑，例如规则 planner、catalog lookup、summary、fact QA 与 control 分支。

第一阶段优先只把现有 `Local` 主聊天问答路径稳定包进 shell。对于 catalog、summary、control 等其它 Local 内部分支，可以先作为兼容节点或 passthrough 节点接入；`Web` 与 `Hybrid` 暂不迁入 shell，继续保持现有调用链路。

原因：

- 当前仓库已有可运行的 planner / QA 主流程，实现基础已经存在；
- `Local` 主聊天问答路径是当前最核心、回归面最大的链路，应该优先稳定；
- 其它路径若同步做深度整理，会把“套壳”演变为“顺手重构内部能力”，超出本次变更边界；
- `Web` 与 `Hybrid` 分别涉及 Gateway 原生联网逻辑和现有混合编排，若同时迁入会把范围从“套壳”扩大成“统一改造所有 mode”；
- 直接把所有底层能力改造成原生 graph 节点会放大迁移成本和回归面；
- 用 shell 包住现有逻辑，可以先稳定入口契约，再逐步把内部步骤模块化。

替代方案：

- 继续把 planner 逻辑直接留在 `qa.py`：短期成本低，但会继续模糊编排层与能力层边界。
- 全量图化 QA 流程：理论上更统一，但一次性迁移风险过高，不符合“壳层优先”的目标。

### 决策 2：统一 planner state 契约，并显式区分 shell 决策字段与 kernel 执行字段

LangGraph state 统一包含请求元信息、planner 决策、执行产物与观测字段，至少包括：

- `request`: sessionId、query、mode、history、traceId
- `planner`: `planner_used`、`planner_source`、`planner_confidence`、`primary_capability`、`strictness`、`action_plan`
- `execution`: `selected_path`、`paper_set`、`short_circuit`、`execution_trace`
- `response`: answer、sources、usage、error

原因：

- 当前 trace 字段已经存在，适合作为 state 对外观测面的基础；
- 后续 Skill 若要接入，需要一个稳定状态容器，而不是继续拼接临时 dict；
- 将“planner 做了什么”与“kernel 执行得到什么”拆开，更利于审计和测试。

替代方案：

- 复用 `qa.py` 内部临时变量直接传递：实现简单，但状态定义不可审计，也无法稳定扩展。

### 决策 3：Gateway 保持协议编排角色，只把聊天请求路由到 planner shell 入口

Gateway 不参与 planner 决策，也不理解具体 Skill 细节；它只负责：

- 接收前端统一聊天事件；
- 对 `Local` 模式调用 Python kernel 的 planner shell 入口；
- 对 `Web` 模式继续走现有 Gateway 原生联网路径；
- 对 `Hybrid` 模式继续走现有混合编排和旧 kernel 入口；
- 继续把 shell 产出的流式消息、sources、messageEnd 和 error 事件透传给前端。

原因：

- Gateway 当前已经承担 WebSocket 协议归一化职责，继续保持“协议层”最稳妥；
- 如果把 planner 判断放到 Gateway，会把 Node 与 Python 的能力边界再次耦合；
- 后续 planner/skill 主要在 Python 侧演进，更适合由 kernel 内部保持单一编排真相源。

替代方案：

- 在 Gateway 做 planner routing：会复制 Python 侧语义，并让双端实现难以同步。
- 前端直接调 kernel planner：会破坏现有通过 Gateway 屏蔽异构后端的部署模型。

### 决策 4：第一阶段采用独立端点灰度，而不是直接替换 `/qa` 与 `/qa/stream`

第一阶段固定采用“双入口兼容 + 独立端点灰度”策略：

- 新增 `/planner/qa` 与 `/planner/qa/stream` 作为 planner shell 独立入口；
- 保留现有 `/qa` 与 `/qa/stream` 不变，作为 `Hybrid` 旧路径和 `Local` 回退路径；
- Gateway 仅在 `Local` 模式优先调用 `/planner/qa*`；
- 当 LangGraph 运行异常、state 校验失败或 planner 节点不可用时，回退到当前 `qa.py` 的最小可用路径。

原因：

- 当前系统已经服务聊天链路，切断旧入口风险过高；
- shell 初期主要解决架构边界，而不是立即替换所有调用面；
- 独立端点可以把“灰度 planner shell”和“保持旧入口稳定”同时做到；
- 回滚时只需让 Gateway 的 `Local` 调用切回旧入口或关闭 planner shell 开关。

替代方案：

- 强制一次性切到新入口：迁移更干净，但回滚成本高。

### 决策 5：第一阶段只强约束最小必需骨架，但允许保留少量内部执行节点

第一阶段只强约束最小必需骨架：

- `load_request_context`
- `plan_chat_request`
- `route_capability`
- `run_local_main_path` 或与其等价的少量内部执行节点
- `fallback_to_legacy_qa`

其中 `route_capability` 只决定下一跳，不直接执行业务；执行节点只消费稳定 state，不自行推导额外调度规则。

第一阶段允许为了保持现有实现最小改动，而在 graph 内保留少量比 `run_local_main_path` 更细的内部节点命名，例如：

- `run_fact_qa_path`
- `run_compat_path`

只要这些节点仍然服务于同一个“Local 主聊天问答路径优先、其它 Local 分支兼容挂接”的边界，就不视为超范围。

第一阶段执行要求：

- `run_local_main_path` 必须作为 `Local` 主聊天问答路径的逻辑边界优先稳定落地；实现上允许用 `run_fact_qa_path` 与 `run_compat_path` 这类少量内部节点承载；
- `Local` 内部若出现 catalog、summary、control 等分支，允许先由该节点内部委托现有函数或兼容入口，不强制拆成独立 graph 节点；
- `Web` 与 `Hybrid` 在第一阶段不强制形成 graph 节点，只要求保留现有链路并与 shell 边界兼容；
- 后续如需让其它路径正式进入 graph，再单独细化节点拆分。

原因：

- 当前 proposal 已明确后续 Skill 要建立在统一 planner shell 之上；
- 过早把未来所有路径命名成正式节点，会给第一阶段实现制造不必要的范围压力；
- 但完全禁止少量内部节点，也会迫使实现为了贴合文档而做无意义重命名；
- 先固定最小骨架，再逐步拆细，能更符合“壳层优先”的目标。

替代方案：

- 只保留两个超大节点（planner / executor）：实现快，但无法形成清晰能力边界。

## 风险 / 权衡

- [LangGraph 壳层增加入口复杂度] → 先复用现有规则 planner 和 QA 主流程，只新增最薄的一层 state graph，避免一次性深改。
- [双入口并存造成行为漂移] → 用统一 trace 字段、相同 fallback 语义和回归测试约束新旧入口输出。
- [Gateway 改路由时破坏现有流式协议] → 保持 `message` / `sources` / `messageEnd` / `error` 事件不变，只替换 Python 侧入口地址与内部实现。
- [state 设计过早固化后续 Skill] → 只固定顶层必需字段，把能力私有数据收敛到 `execution` 子对象，保留扩展空间。
- [shell 故障导致聊天不可用] → 提供开关与 legacy QA 回退节点，保证 planner shell 不是单点故障。

## 迁移计划

1. 在 Python kernel 内新增 LangGraph planner shell 模块，定义统一 state、最小必需节点和独立 `/planner/qa*` 入口。
2. 让 shell 的 planner 节点先复用现有 `app/capability_planner.py` 规则 planner，并优先把现有 `Local` 主聊天问答路径稳定接入 shell。
3. `Local` 内部遇到 catalog / control / summary 等分支时，先复用现有 `qa.py` / 现有能力函数或兼容入口，不要求第一阶段拆成独立 graph 节点。
4. `Web` 保持 Gateway 原生联网路径，`Hybrid` 保持现有混合编排和旧 kernel 入口，不接入 shell。
5. 为 shell 输出补齐与现有 run trace 对齐的 planner / execution 观测字段。
6. 更新 Gateway 聊天服务与适配器，仅让 `Local` 请求优先发往 `/planner/qa*`；保留其它 mode 现有行为。
7. 通过回归测试验证 `Local` 模式下的流式回答、sources、短路、回退与错误事件行为，并验证 `Web` / `Hybrid` 未被本次变更破坏。

回滚策略：

- 让 Gateway 的 `Local` 请求改回 legacy `/qa` / `/qa/stream`；
- 保留新增 `/planner/qa*` 模块但不走流量；
- trace 字段继续输出默认值，避免上层消费者崩溃。

实现说明：

- 第一阶段允许由 `kernel_api` 在 shell 执行完成后，把 `planner_shell_used`、`selected_path`、`execution_trace`、`short_circuit`、`truncated` 等观测字段合并写回 `run_trace.json` 与 `qa_report.json`。
- 这仍满足“shell 对外产出统一观测字段”的要求，只是落盘职责暂由 shell 外围的 API 适配层承担。

## 开放问题

- LangGraph 节点内部是否需要同时支持同步回答与流式回答两种 response composer，还是只统一在 stream 入口上实现？
- 后续 Skill 接入时，`execution_trace` 是继续使用通用数组结构，还是需要升级为强类型步骤模型？
