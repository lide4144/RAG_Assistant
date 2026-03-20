# llm-planner-decision-validation 规范

## 目的
定义 LLM planner decision 进入 planner runtime 前的运行时校验关口、拒绝原因和 shadow 对比记录，确保 llm-first planner source 在迁移期可受控执行、可受控结束且可评估。

## 需求
### 需求:系统必须为 LLM planner decision 提供运行时校验关口
系统必须在 LLM planner 输出进入 planner runtime 执行前提供独立的运行时校验关口，并将校验结果限制为 `accept`、`accept_with_warnings` 或 `reject`；禁止让未经校验的 LLM decision 直接驱动 tool 准备、路径选择或用户可见响应。

#### 场景:校验通过后进入运行时
- **当** LLM planner 输出结构化 decision 且通过所有必需校验
- **那么** runtime 必须将其视为正式 planner decision 并继续进入 tool 准备与路由阶段

#### 场景:校验失败时拒绝直接执行
- **当** LLM planner 输出缺少必需字段、结构非法或命中策略禁止规则
- **那么** runtime 必须拒绝该 decision，并进入受控结束，而不是继续按该结果执行

### 需求:系统必须按结构、语义、执行与策略四层校验 LLM decision
系统必须至少按结构合法性、语义一致性、执行合法性与策略合法性四层校验 LLM planner decision，并为每次 `reject` 或 `accept_with_warnings` 记录稳定 reason code；禁止仅用单个布尔标记表达校验结果。

#### 场景:结构校验发现非法枚举
- **当** LLM planner 输出的 `decision_result`、`strictness` 或其他枚举字段不在受支持集合中
- **那么** runtime 必须将该 decision 标记为 `reject` 并记录结构类拒绝原因

#### 场景:执行校验发现未注册 action
- **当** LLM planner 的 `action_plan` 包含 registry 中不存在的 action
- **那么** runtime 必须将该 decision 标记为 `reject` 并记录执行类拒绝原因

### 需求:系统必须在校验失败时进入受控结束而非规则回退
当 `LLM planner decision` 被运行时校验拒绝时，系统必须直接进入受控结束路径，并保留完整 rejection 观测字段；禁止优先尝试使用 `rule planner` 产出兼容 decision，也禁止在 reject 后继续隐式脑补默认字段使其“凑合可跑”。

#### 场景:LLM decision 被拒绝后直接停止正式执行
- **当** `LLM planner decision` 被 validation gate 拒绝
- **那么** runtime 必须停止该 decision 的正式执行，并进入受控结束路径，而不得改用 `rule planner decision`

#### 场景:拒绝后不隐式补全字段
- **当** `LLM planner decision` 缺少必需字段或命中策略禁止规则
- **那么** 系统必须记录稳定 rejection reason 并进入受控结束路径，而不得补全默认字段后继续执行

### 需求:系统必须让 validation reject 产出稳定的受控结束原因
系统必须在 `LLM planner decision` 被 reject 时输出稳定的 `rejection_reason`、`rejection_layer` 与受控结束类型，以便运行时和观测系统能够区分结构失败、策略失败、执行失败或系统异常；禁止只记录单个布尔失败标志。

#### 场景:拒绝原因可审计
- **当** validation gate 拒绝一条 `LLM planner decision`
- **那么** trace 中必须能够看到拒绝层级、原因代码和对应的受控结束类型

### 需求:系统必须支持与规则结果隔离的 shadow 对比记录
系统可以支持 `shadow_compare` 或等价诊断模式，在不改变用户主执行路径的前提下记录 `LLM planner decision`、validation 结果与人工诊断结论；禁止让 shadow 结果被提升为本轮正式执行来源，也禁止继续依赖 rule baseline 作为对比输入。

#### 场景:shadow 仅用于诊断
- **当** 系统运行在 `shadow_compare` 或等价诊断模式下
- **那么** 同一请求可以记录 `LLM planner decision`、validation 结果与人工诊断结论，但正式执行来源必须仍然只来自通过校验的 `LLM planner decision`

#### 场景:shadow 模式不允许接管主回答
- **当** 诊断模式下存在额外 shadow 记录
- **那么** 用户本轮主回答必须仍由正式 `LLM planner` 执行链产生，而不是因 shadow 记录切换主路径

### 需求:系统必须为 shadow 评估记录诊断结论与人工评审标签位
系统必须为 shadow mode 记录 `LLM planner decision`、validation 结果与人工评审标签位，并支持 `accepted`、`needs_followup`、`incorrect` 或 `blocked` 等不依赖规则基线的诊断结论；禁止继续记录或依赖 rule baseline 对比字段。

#### 场景:人工评审结果可写回
- **当** 运维或评测对某条 shadow 样本完成人工判断
- **那么** 系统必须能够为该样本记录稳定的评审标签，用于后续灰度决策
