## 为什么

当前系统已经具备稳定的 `frontend -> gateway -> python kernel` 主链路，但在多轮上下文理解、意图判断与能力选择上仍偏规则化，导致“他们/这些论文”等省略表达、复杂研究请求和多能力组合场景表现不稳定。项目需要引入一个顶层编排壳层来承接 Planner/Skill 逻辑，但不应推翻现有确定性 Pipeline。

## 变更内容

- 在 Python 侧引入基于 `LangGraph` 的顶层 Planner 壳层，用于承接聊天请求的前置理解与路由。
- 保持现有 Kernel 核心能力接口不变，Planner 仅负责选择调用路径，不重写底层导入、索引、检索、建图与引用链路。
- 明确 Planner 与现有 Kernel 的职责边界：Planner 负责“做什么”，Kernel 负责“如何稳定完成”。
- 第一阶段仅对 `Local` 主聊天问答路径启用 Planner 壳层；`Web` 保持 Gateway 原生路径，`Hybrid` 继续旧的 Kernel 路径，不要求同等深度重整。
- 第一阶段采用独立 `/planner/qa`、`/planner/qa/stream` 端点灰度，而不是直接替换现有 `/qa`、`/qa/stream`。
- 为后续 Skill 接入预留统一的状态对象、节点命名与能力入口约定。

## 功能 (Capabilities)

### 新增功能
- `capability-planner-execution`: 定义顶层 Planner 的执行边界、状态管理、节点调用约束与失败回退原则。

### 修改功能
- `node-gateway-orchestration`: 明确 Gateway 如何把聊天请求转发到 Planner 壳层，并保持现有聊天与任务主链路兼容。

## 影响

- 后端架构：新增一层 Planner 壳层，但不替换现有 Kernel 能力模块。
- 调用边界：需要定义 Planner 到 Kernel 的稳定能力接口。
- 设计约束：后续 Skill 与路由变更应建立在统一 Planner 壳层之上，避免继续在 Gateway 或零散规则里扩张。
