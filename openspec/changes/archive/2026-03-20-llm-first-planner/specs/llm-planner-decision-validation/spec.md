## 新增需求

### 需求:系统必须让 validation reject 产出稳定的受控结束原因
系统必须在 `LLM planner decision` 被 reject 时输出稳定的 `rejection_reason`、`rejection_layer` 与受控结束类型，以便运行时和观测系统能够区分结构失败、策略失败、执行失败或系统异常；禁止只记录单个布尔失败标志。

#### 场景:拒绝原因可审计
- **当** validation gate 拒绝一条 `LLM planner decision`
- **那么** trace 中必须能够看到拒绝层级、原因代码和对应的受控结束类型

## 修改需求

### 需求:系统必须在校验失败时进入受控结束而非规则回退
当 `LLM planner decision` 被运行时校验拒绝时，系统必须直接进入受控结束路径，并保留完整 rejection 观测字段；禁止优先尝试使用 `rule planner` 产出兼容 decision，也禁止在 reject 后继续隐式脑补默认字段使其“凑合可跑”。

#### 场景:LLM decision 被拒绝后直接停止正式执行
- **当** `LLM planner decision` 被 validation gate 拒绝
- **那么** runtime 必须停止该 decision 的正式执行，并进入受控结束路径，而不得改用 `rule planner decision`

#### 场景:拒绝后不隐式补全字段
- **当** `LLM planner decision` 缺少必需字段或命中策略禁止规则
- **那么** 系统必须记录稳定 rejection reason 并进入受控结束路径，而不得补全默认字段后继续执行

### 需求:系统必须支持与规则结果隔离的 shadow 对比记录
系统可以支持 `shadow_compare` 或等价诊断模式，在不改变用户主执行路径的前提下记录 `LLM planner decision`、validation 结果与人工诊断结论；禁止让 shadow 结果被提升为本轮正式执行来源，也禁止继续依赖 rule baseline 作为对比输入。

#### 场景:shadow 仅用于诊断
- **当** 系统运行在 `shadow_compare` 或等价诊断模式下
- **那么** 同一请求可以产出 `LLM planner decision`、validation 结果与人工诊断结论，但正式执行来源必须仍然只来自通过校验的 `LLM planner decision`

#### 场景:shadow 模式不允许接管主回答
- **当** 诊断模式下存在额外 shadow 记录
- **那么** 用户本轮主回答必须仍由正式 `LLM planner` 执行链产生，而不是因 shadow 记录切换主路径

## 移除需求
