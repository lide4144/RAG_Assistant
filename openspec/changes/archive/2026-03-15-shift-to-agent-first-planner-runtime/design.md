## 上下文

当前仓库已经完成 `introduce-langgraph-planner-shell`，并在代码中落下了第一阶段基础：

- `app/planner_shell.py` 提供了 LangGraph 顶层 graph、统一 state 和 `/planner/qa*` 入口；
- `app/capability_planner.py` 仍以规则规划为主，输出 `primary_capability`、`strictness`、`action_plan` 与 fallback 字段；
- `gateway/src/adapters/pythonKernelClient.ts` 已让 `Local` 模式优先请求 `/planner/qa`，并在 planner 入口不可用时回退到 `/qa`；
- 底层 kernel 仍负责事实问答、catalog、summary、control、citation、trace 和任务类能力。

这意味着系统已经拥有一个“可运行的 planner shell”，但其规范定义仍偏保守：它更像一个受控路由壳，而不是正式的 LLM-first planner runtime。仓库中的 `docs/agent-first-transition-plan.md` 已经明确新路线，即由顶层 LLM Planner 负责操作理解、工具选择、澄清和降级，而确定性 kernel 退到工具与安全执行层。

本次变更的目标不是立即实现完整 agent，也不是引入新的前端协议、事件类型或具体 tool，而是把现有壳层正式重定义为 agent-first runtime，并把未来实现必须遵守的层级边界固定下来。

约束：

- 必须复用现有 `frontend -> gateway -> python kernel` 主链路。
- 不做新的前端 UI 变更。
- 不展开具体 gateway agent 事件协议。
- 不直接实现新的 tool，只定义 tool contract 和边界。
- 必须保留 evidence gate、citation contract、任务状态与 legacy fallback，不能让“agent-first”削弱现有硬约束。

## 目标 / 非目标

**目标：**

- 将现有 LangGraph shell 正式定义为顶层 `LLM Planner runtime`，而不是临时兼容壳层。
- 明确三层职责边界：`LLM Planner`、`tool 层`、`确定性 pipeline / kernel`。
- 定义 planner runtime 与现有 kernel 的关系：planner 决定“调用什么和何时停止”，kernel 保证“如何稳定执行与安全落盘”。
- 定义失败回退、安全边界和运行时降级原则，保证 planner runtime 不是新的单点故障。
- 为后续 `tool selection`、`kernel tools`、`agent observability` 等变更提供统一架构前提。

**非目标：**

- 不在本次变更中把规则 planner 直接替换成 LLM planner 实现。
- 不在本次变更中新增或改造具体 tool。
- 不定义前端如何展示 planning / tool-running 状态。
- 不定义新的 gateway 高层 agent 事件帧格式。
- 不要求一次性重写 `qa.py` 内部所有能力实现。

## 决策

### 决策 1：将 LangGraph shell 升级为顶层 planner runtime，而非继续定义为“兼容壳层”

现有 `app/planner_shell.py` 已经具备统一 state、路由节点和 fallback 入口，但规范层面仍把它描述为“第一阶段壳层”。本次变更要求将其升级为正式的顶层 planner runtime：

- 所有 agent-first 聊天编排必须以该 runtime 作为唯一顶层入口；
- 无论后续 planner 核心是规则、LLM 或混合实现，对外都通过同一 runtime state、route 和 observation 契约暴露；
- `qa.py`、catalog、summary、control 等能力不再直接代表“顶层理解层”，只作为 runtime 可调度执行单元存在。

原因：

- 现有代码已经证明 shell 入口和 gateway fallback 可以工作；
- 如果仍把它定义成“临时壳层”，后续变更会继续把理解逻辑散落到 `qa.py`、Gateway 或某些 skill 入口；
- 先固定 runtime 真相源，后续才能安全替换内部 planner 实现。

替代方案：

- 继续维持“受控壳层”定义：短期文档改动最少，但会继续模糊顶层责任归属。
- 等到真实 LLM planner 落地后再升级定义：会导致多个后续变更在不同架构前提上并行推进，风险更高。

### 决策 2：明确三层职责边界为 Planner、Tool、Deterministic Pipeline

系统按以下边界演进：

1. `LLM Planner runtime`
   - 负责用户意图理解、上下文吸收、澄清判断、tool 选择、执行顺序、停止条件和降级决策；
   - 不直接执行数据检索、证据拼接、引用绑定和任务落盘。
2. `Tool 层`
   - 向 planner 暴露可调用能力单元，例如 catalog lookup、summary、fact QA、control、research assistant 组合能力；
   - 接收结构化输入，返回结构化结果、错误信息和可观测元数据；
   - 不自行提升为顶层自由规划器。
3. `Deterministic pipeline / kernel`
   - 负责索引、检索、建图、重排、evidence gate、citation、任务状态、落盘、可观测 trace；
   - 作为 tool 的内部稳定执行引擎存在；
   - 对 planner 暴露受约束的输入输出，不泄露实现细节给 Gateway 或前端。

原因：

- 用户要求的是架构重定义，而不是简单把 rule planner 改成 LLM；
- 当前仓库的核心价值在于确定性 pipeline 和 citation/evidence 约束，不能被 agent 化吞没；
- 未来若不先定义 tool 层，planner 会直接耦合具体 kernel 内部函数，导致后续替换困难。

替代方案：

- Planner 直接调用 kernel 内部流程：实现快，但会把稳定执行与顶层决策耦合在一起。
- 把 tool 层放到 Gateway：会让 Node 侧复制 Python 语义，破坏单一真相源。

### 决策 3：Planner runtime 必须支持“规划器可替换，外部契约稳定”

runtime 的外部契约必须固定为统一 state、tool call envelope、执行观察字段和 fallback 语义。内部 planner 可以经历三种阶段：

- 当前的规则 planner；
- 未来的 LLM planner；
- 受策略控制的混合 planner。

无论内部采用哪一种，外部都必须稳定输出：

- planner decision：意图、能力、严格度、tool 选择、澄清/停止/降级决定；
- execution trace：调用顺序、结果摘要、失败原因、fallback 标记；
- response contract：回答、sources、usage、错误与安全标记。

原因：

- 当前仓库已经依赖 `run_trace`、`sources`、`messageEnd` 等稳定产物；
- 如果 planner 升级会连带改变 Gateway 或前端契约，迁移面会无必要扩大；
- 稳定 envelope 是未来把 kernel 能力逐步暴露成 tools 的前提。

替代方案：

- 让每类 planner 自己定义输出：灵活，但会导致后续 gateway、评测、观测失去统一基线。

### 决策 4：失败回退分为“planner 降级”和“tool/pipeline 降级”，禁止无边界自治

agent-first 不意味着 planner 可以无限步试错。本次变更固定两类回退：

- `planner 降级`：规划失败、置信不足、状态不完整、策略判定不适合 agent 执行时，runtime 必须降级到 legacy QA 或受限 deterministic path；
- `tool/pipeline 降级`：单个 tool 调用失败、结果为空、证据不足、citation 不满足时，runtime 必须停止后续依赖步骤，改为受控失败、澄清或 fallback answer。

同时固定以下硬边界：

- 计划步数必须有上限；
- 未注册 tool 禁止被调用；
- tool 结果若未满足 evidence/citation contract，禁止直接组装最终回答；
- planner 禁止绕过 kernel 的 evidence gate、citation、任务状态与审计字段。

原因：

- 当前系统最大的可靠性来自确定性安全边界；
- 如果只强调 agent 灵活性，不定义回退层级，后续实现很容易出现“planner 自行补答案”或“tool 失败后继续硬拼接”的行为。

替代方案：

- 只保留统一 fallback：实现简单，但无法区分是 planner 失败还是 tool 失败，诊断能力不足。
- 允许 planner 自主重试任意 tool：灵活但失控，且超出当前系统需要的边界。

### 决策 5：Gateway 继续作为协议入口，不承担 planner 语义和 tool 细节

`gateway` 继续负责：

- 统一前端 WebSocket / HTTP 入口；
- 把 `Local` 聊天请求发送到 planner runtime；
- 维持 `Web`、`Hybrid` 与其他任务链路的兼容；
- 对前端保持既有聊天事件协议。

Gateway 不负责：

- 推断用户意图；
- 选择 tool；
- 解释 planner 内部状态；
- 定义 agent 高层事件语义。

原因：

- 现有 `gateway/src/adapters/pythonKernelClient.ts` 已采用 planner 优先、legacy fallback 的最小职责模型；
- 让 Gateway 知道更多 planner 细节，会形成 Node/Python 双实现。

替代方案：

- 在 Gateway 做顶层 agent routing：会让架构再次分叉。

### 决策 6：论文助理模式重定义为 Planner 可调度能力，而非旁路产品模式

`paper-assistant-mode` 现有规范强调回答风格和澄清策略，但在 agent-first 路线下，它必须被视为 planner 可选择、可停止、可回退的一类高层能力，而不是绕开 planner 的独立模式。

这意味着：

- planner 必须决定何时进入研究辅助能力；
- 论文助理输出仍必须经过 tool/pipeline 的 evidence 与 citation 约束；
- 当研究辅助能力条件不满足时，planner 必须选择澄清、降级或转回普通事实问答，而不是直接继续扩展。

原因：

- 用户目标之一是明确与现有 kernel 的关系；
- 研究辅助是最容易把“能力模式”误写成“顶层旁路”的地方，必须提前收边界。

替代方案：

- 继续把 paper assistant 当作独立模式：会削弱 planner 的顶层统一性。

## 风险 / 权衡

- [agent-first 定义先于真实 LLM planner 实现] → 先固定 runtime 契约与边界，不承诺立即替换规则 planner。
- [tool 层尚未实体化，规范可能过早] → 仅固定 tool contract 和职责，不预定义具体 tool 列表与实现细节。
- [双重回退链路增加复杂度] → 在观测字段中区分 planner fallback 与 tool/pipeline fallback，并保持 Gateway 仍只认稳定响应契约。
- [旧 skill-first 变更继续按旧定义推进] → 在 proposal/spec 中明确只有 `introduce-langgraph-planner-shell` 作为底座保留，其他相关变更需要按 agent-first 重新定义。
- [paper assistant 等高层能力边界模糊] → 将其纳入 planner runtime 管辖，并要求任何高层能力都不能绕过 kernel 安全门控。

## 迁移计划

1. 先通过本变更更新 proposal、design、specs、tasks，把 agent-first runtime 定义变成正式规范。
2. 将 `capability-planner-execution` 从“planner shell + 受限执行器”升级为“LLM Planner runtime + tool boundary + deterministic guardrails”。
3. 将 `node-gateway-orchestration` 固定为协议入口和 planner runtime 转发层，不扩展为 planner 语义层。
4. 将 `paper-assistant-mode` 补充为 planner 可调度能力边界，避免后续研究辅助能力绕开 runtime。
5. 后续新变更按顺序推进：
   - `add-llm-planner-tool-selection-policy`
   - `expose-kernel-capabilities-as-agent-tools`
   - `add-agent-safe-fallback-and-guardrails`
   - 其余 gateway/UI/observability 变更
6. 在实现阶段保持 `/planner/qa*` 与 legacy `/qa*` 的兼容回退，直到新的 planner/tool 体系达到可替换门槛。

回滚策略：

- 如果后续 agent-first 实现证明不成熟，系统仍可暂时继续使用现有规则 planner 和 legacy QA；
- 本次变更本身只更新架构产出物，不引入不可逆代码迁移，因此回滚成本仅为规范层回退。

## 开放问题

- tool contract 的最小统一返回结构是否应在下一变更中单独定义为共享 schema，而不是散落在各 tool 规范中？
- planner runtime 未来是否需要显式区分“澄清问题”与“受控失败回答”两类终止状态？
- `Web` 与 `Hybrid` 最终是否要纳入同一 planner runtime，还是长期保持 Gateway 原生编排？
