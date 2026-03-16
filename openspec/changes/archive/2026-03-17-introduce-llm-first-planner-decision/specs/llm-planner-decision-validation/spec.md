## 新增需求

### 需求:系统必须为 LLM planner decision 提供运行时校验关口
系统必须在 LLM planner 输出进入 planner runtime 执行前提供独立的运行时校验关口，并将校验结果限制为 `accept`、`accept_with_warnings` 或 `reject`；禁止让未经校验的 LLM decision 直接驱动 tool 准备、路径选择或用户可见响应。

#### 场景:校验通过后进入运行时
- **当** LLM planner 输出结构化 decision 且通过所有必需校验
- **那么** runtime 必须将其视为正式 planner decision 并继续进入 tool 准备与路由阶段

#### 场景:校验失败时拒绝直接执行
- **当** LLM planner 输出缺少必需字段、结构非法或命中策略禁止规则
- **那么** runtime 必须拒绝该 decision，并进入受控 fallback，而不是继续按该结果执行

### 需求:系统必须按结构、语义、执行与策略四层校验 LLM decision
系统必须至少按结构合法性、语义一致性、执行合法性与策略合法性四层校验 LLM planner decision，并为每次 `reject` 或 `accept_with_warnings` 记录稳定 reason code；禁止仅用单个布尔标记表达校验结果。

#### 场景:结构校验发现非法枚举
- **当** LLM planner 输出的 `decision_result`、`strictness` 或其他枚举字段不在受支持集合中
- **那么** runtime 必须将该 decision 标记为 `reject` 并记录结构类拒绝原因

#### 场景:执行校验发现未注册 action
- **当** LLM planner 的 `action_plan` 包含 registry 中不存在的 action
- **那么** runtime 必须将该 decision 标记为 `reject` 并记录执行类拒绝原因

### 需求:系统必须在校验失败时优先回退到 rule planner
当 LLM planner decision 被运行时校验拒绝时，系统必须优先尝试使用 rule planner 产出兼容 decision；仅当 rule planner 不可用或也失败时，系统才允许进入 legacy fallback。系统禁止在 LLM decision 被拒绝后继续隐式脑补默认字段使其“凑合可跑”。

#### 场景:LLM decision 被拒绝但 rule planner 可用
- **当** LLM planner decision 被 validation gate 拒绝且 rule planner 仍可运行
- **那么** runtime 必须改用 rule planner decision 完成本轮请求，并记录该次拒绝与回退原因

#### 场景:LLM 与 rule planner 均不可用
- **当** LLM planner decision 被拒绝且 rule planner 同样无法产出有效 decision
- **那么** runtime 必须进入 legacy fallback，并保持请求可受控结束

### 需求:系统必须支持 shadow mode 的 planner 对比记录
系统必须支持 `shadow_compare` 模式，在不改变用户主执行路径的前提下同时记录 rule planner decision、LLM planner decision、validation 结果与字段级差异；禁止 shadow mode 影响最终用户回答。

#### 场景:shadow 模式并行记录两份决策
- **当** 系统运行在 `shadow_compare` 模式下
- **那么** 同一请求必须同时产出 rule planner 与 LLM planner 的 decision 记录，并标记实际执行来源

#### 场景:shadow 模式不改变用户主回答
- **当** 系统运行在 `shadow_compare` 模式下且 LLM planner 给出不同 decision
- **那么** 用户本轮主回答必须仍由既定执行来源产生，而不是因 shadow 记录改变输出结果

### 需求:系统必须为 shadow 评估记录字段级差异与人工评审标签位
系统必须为 shadow mode 记录至少 `primary_capability`、`strictness`、`decision_result`、`requires_clarification`、`selected_tools_or_skills` 与 `action_plan` 的字段级差异，并预留人工评审标签位用于标记 `llm_better`、`rule_better`、`tie` 或 `both_bad`；禁止只记录原始 decision 而不记录可聚合差异。

#### 场景:关键字段差异可聚合
- **当** rule planner 与 LLM planner 在同一请求上给出不同 decision
- **那么** shadow 记录必须能明确指出发生差异的关键字段，而不是仅保留两份原始 JSON

#### 场景:人工评审结果可写回
- **当** 运维或评测对某条 shadow 样本完成人工判断
- **那么** 系统必须能够为该样本记录稳定的评审标签，用于后续灰度决策
